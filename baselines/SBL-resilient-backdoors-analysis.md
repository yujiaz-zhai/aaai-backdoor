# SBL-resilient-backdoors 代码分析报告

> ECCV 2024 | Flatness-aware Sequential Learning Generates Resilient Backdoors

---

## 1. 项目概述

**核心问题**：传统后门攻击（CBL）训练出的模型容易被微调防御消除后门，原因是深度神经网络存在灾难性遗忘（Catastrophic Forgetting），微调会把模型推出后门区域。

**解决方案**：SBL 将后门训练重新建模为持续学习（CL）的两阶段过程：
1. **Task 0（混合任务）**：用包含投毒样本和干净样本的混合数据集训练后门模型
2. **Task 1（纯干净任务）**：在未见干净数据上训练，利用 CL 正则化方法防止对后门的遗忘

**关键创新**：
- 利用 CL 技术将后门"锁定"在损失地形的宽广区域
- 配合 SAM（Sharpness-Aware Minimization）优化器寻找更平坦的后门区域
- 结果：后门模型对微调防御具有抗性（resilient）

---

## 2. 目录结构

```
SBL-resilient-backdoors/
├── main.py                    # 主入口：SBL 后门训练
├── run_defense.py             # 防御评估入口：加载后门模型并应用防御
├── sam.py                     # SAM (Sharpness-Aware Minimization) 优化器实现
├── requirements.txt           # 依赖清单
├── README.md                  # 项目说明
├── run_cifar.sh               # CIFAR-10 实验脚本（训练+防御）
├── run_gtsrb.sh               # GTSRB 实验脚本（训练+防御）
│
├── backbones/                 # 骨干网络（特征提取器+分类头）
│   ├── mlp.py                 # 简单全连接网络
│   ├── resnet.py              # ResNet-18/34/50/101/152（标准版）
│   ├── preact_resnet.py       # Pre-activation ResNet
│   ├── light_resnet.py        # 轻量 ResNet（用于 CIFAR 的原始设计）
│   └── vgg.py                 # VGG-11/13/16/19
│
├── models/                    # 持续学习（CL）方法封装
│   ├── base_model.py          # CL 模型基类（抽象）
│   ├── training.py            # 核心训练循环（train, train_epoch, test_model）
│   ├── naive.py               # Naive（无正则化基线）
│   ├── ewc.py                 # EWC（弹性权重巩固）
│   ├── anchor.py              # Anchoring（锚点蒸馏）
│   ├── agem.py                # A-GEM（梯度投影方法）
│   └── joint.py               # Joint Training（联合训练基线）
│
├── data/                      # 数据加载和触发器注入
│   ├── dataset.py             # 数据集构建、触发器注入、DataLoader 组装
│   ├── utils.py               # 工具（WaNet 网格生成、batch 可视化）
│   └── hello_kitty.jpeg       # Blended 攻击的触发器图片
│
├── defenses/                  # 后门防御方法
│   ├── finetuning.py          # Fine-tuning 防御（SGD 微调）
│   ├── ft_sam.py              # SAM Fine-tuning 防御（用 SAM 微调）
│   ├── nad.py                 # NAD（Neural Attentive Distillation）防御
│   └── pruning.py             # 剪枝防御（基于通道激活大小）
│
└── utils/                     # 工具函数
    ├── arguments.py           # 命令行参数定义
    ├── load.py                # 模型/优化器/检查点加载与保存
    ├── logger.py              # 日志配置
    ├── sam_utils.py           # SAM 辅助函数（BN 动量开关）
    └── loss_landscape.py      # 损失地形可视化
```

---

## 3. 完整调用链

### 3.1 训练流程

```
main.py::main(args)
  ├── load_all_path(args)                        # 构建日志和检查点路径
  ├── get_dat_dataloader(args)                   # 构建数据（DAT模式）
  │     返回: mixed_loader, clean_loader, finetune_loader, test_loaders, trigger
  ├── load_backbone(args.backbone, ...)           # 加载骨干网络
  ├── load_optimizer_and_scheduler(net, args)     # 加载优化器+调度器
  ├── SAM(params, SGD, lr, momentum)              # 若 opt_mode==sam，包装为 SAM
  ├── load_model(backbone, criterion, ...)        # 根据 cl_method 创建 CL 模型实例
  │     → EWC / Anchor / AGem / Naive / Joint
  │
  └── train(model, dataloaders, testloaders, epochs, device, args)
        │
        └── for task_id in [0, 1]:                # 遍历两个任务
              ├── load_checkpoint()               # 若 is_load，尝试加载第一个任务的 checkpoint
              ├── for epoch in range(epochs):
              │     └── train_epoch(model, dataloader, epoch, device, args)
              │           ├── dynamically_add_trigger(inputs, labels, args)  # DAT模式
              │           └── model.observe(inputs, targets, is_poisoned)
              │                 ├── enable/disable_running_stats()
              │                 ├── SAM.first_step() / second_step()
              │                 └── penalty() / project() / store_grad()
              ├── test_model()                    # 每个 epoch 评估干净/投毒准确率
              ├── save_checkpoint()               # 保存第一个任务的模型
              ├── model.end_task(dataloader)       # CL 正则化
              └── 更新 optimizer 为 sec_optimizer  # 第二任务用不同学习率
```

### 3.2 防御评估流程

```
run_defense.py::main()
  ├── (同 main.py 的数据/模型加载流程)
  ├── load_checkpoint()                           # 加载已训练的后门模型
  └── for defense_method in defenses:
        ├── ft:      finetuning()               # defenses/finetuning.py
        ├── nad:     NAD()                      # defenses/nad.py
        ├── pruning: pruning()                  # defenses/pruning.py
        └── sam_ft:  finetuning_sam()           # defenses/ft_sam.py
```

---

## 4. 核心算法详解

### 4.1 SAM 优化器 (sam.py)

SAM 在参数空间中寻找损失地形更平坦的区域：

```
first_step():
    grad_norm = ||∇L(w)||₂
    for each parameter p:
        ε(w) = ρ / (grad_norm + 1e-12) * ∇L(p)
        p ← p + ε(w)                              # 爬升到局部最大值

second_step():
    for each parameter p:
        p ← old_p                                  # 回退到原始点
    base_optimizer.step()                           # 在 w 处执行 SGD 更新
```

### 4.2 CL 方法实现

#### EWC (Elastic Weight Consolidation)

```python
end_task(dataloader):
    fish = 0
    for each sample (x, y):
        loss = -log_softmax(y | x)
        exp_cond_prob = mean(exp(loss))
        fish += exp_cond_prob * (∇L)²              # Fisher 信息矩阵对角近似
    self.fish = γ * self.fish + fish               # 累积
    self.checkpoint = current_params.clone()

penalty():
    return Σ( fish * (θ - checkpoint)²)
```

#### Anchoring

```python
end_task(dataloader):
    self.anchor_model = deepcopy(model)

penalty(inputs, outputs, is_poisoned):
    anchor_outputs = anchor_model(inputs)
    loss = MSE(softmax(outputs), softmax(anchor_outputs))
    return mean(loss * (1 - is_poisoned))
```

#### A-GEM

```python
observe(inputs, labels):
    loss = CE(model(inputs), labels)
    loss.backward()
    store_grad(model.parameters, grad_xy)

    buf_inputs, buf_labels = sample_buffer()
    loss_buf = CE(model(buf_inputs), buf_labels)
    loss_buf.backward()
    store_grad(model.parameters, grad_er)

    if dot(grad_xy, grad_er) < 0:
        grad_xy = project(grad_xy, grad_er)
    overwrite_grad(model.parameters, grad_xy)
    optimizer.step()
```

### 4.3 数据分割策略

训练集按 `task_portion=[0.05, 0.1, 0.85]` 分割：

```
┌──────────────────────────────────────────────────────────────────────┐
│ mixed (85%)                │ unseen clean (10%) │ finetune (5%)     │
│ ┌──poisoned──┬──clean─────┐│                    │                   │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.4 支持的攻击方法

| 方法 | 实现描述 |
|------|---------|
| `badnet` | 在右下角叠加 `trigger_size x trigger_size` 的可学习触发器图案 |
| `blended` | 将 hello_kitty 图片以 0.2 透明度与输入混合 |
| `wanet` | 使用网格扭曲（grid_sample）进行 warping 攻击 |
| `sig` | 叠加 sin 波纹图案（delta=20, f=6） |

### 4.5 防御方法

#### Fine-tuning
在未见过的干净数据上用标准 SGD 微调后门模型。

#### SAM Fine-tuning
使用 SAM 优化器在干净数据上微调（两步更新模式）。

#### NAD (Neural Attentive Distillation)
```
阶段 1: 训练 Teacher（在干净数据上微调后门模型）
阶段 2: NAD 蒸馏
  student_output = student(inputs)
  teacher_output = teacher(inputs)（frozen）
  loss = CE(student_output, targets)
  AT_loss = Σ β_i * MSE(attn_map(student_i), attn_map(teacher_i))
  attn_map(fm) = Σ |fm|^p / ||Σ |fm|^p||_2    # p=2.0
```

目标层：ResNet-18 → layer2, layer3, layer4

#### Pruning
对最后一层卷积的通道按激活大小排序，逐个剪枝评估。

---

## 5. 命令行参数

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `--dataset` | mnist | 数据集：mnist/cifar10/gtsrb/celebA/imagenet10 |
| `--backbone` | simpleMLP | 骨干网络 |
| `--cl_method` | ewc | 持续学习方法：naive/ewc/anchor/agem/joint |
| `--lambd` | 1 | CL 正则化项系数 |
| `--buffer_size` | 256 | A-GEM 的 buffer 大小 |
| `--opt_mode` | normal | 优化器模式：normal/sam |
| `--lr` | 0.1 | 第一任务学习率 |
| `--sec_lr` | 0.001 | 第二任务学习率 |
| `--finetune_lr` | 0.001 | 防御微调学习率 |
| `--epochs` | 150 | 第一任务训练轮数 |
| `--sec_epochs` | 100 | 第二任务训练轮数 |
| `--finetune_epochs` | 50 | 防御微调轮数 |
| `--task_portion` | [0.05, 0.1, 0.85] | [finetune, unseen_clean, mixed] |
| `--mixed_first` | False | True=先训练混合数据 |
| `--is_dat` | False | 是否使用动态触发器注入 |
| `--poisoning_method` | badnet | 攻击方法 |
| `--poisoning_rate` | 0.1 | 投毒比例 |
| `--target_label` | 0 | 目标标签 |
| `--trigger_size` | 3 | 触发器尺寸 |
| `--defenses` | [ft,nad] | 防御方法列表 |
| `--lr_scheduler` | CosineAnnealingLR | 学习率调度器 |

---

## 6. Shell 脚本说明

### run_cifar.sh / run_gtsrb.sh

每个脚本包含 3 个实验阶段：

**阶段 1：Baseline（原始 BadNets）**
- `cl_method=joint`，不使用 SAM，不使用 DAT

**阶段 2：SBL + Naive/EWC**
- `cl_method=naive` 和 `cl_method=ewc`
- 使用 SAM 优化器（`--opt_mode sam`）
- 使用 DAT 动态触发器（`--is_dat`）

**阶段 3：防御评估**
- 加载阶段 2 训练好的模型，依次应用 ft、nad、sam_ft 三种防御

---

## 7. 关键设计要点

1. **两阶段训练是核心**：混合数据训练 + CL 正则化下的干净数据训练，利用灾难性遗忘的反面锁定后门
2. **SAM 发挥双重角色**：攻击阶段寻找平坦后门区域；防御阶段作为 SAM Fine-tuning 防御方法
3. **数据分割策略**：训练集按 task_portion 分割，确保两任务用不同数据子集
4. **注意**：`utils/load.py` 引用了 `models.si` 和 `models.mas`，但这两个文件不存在，使用 `si`/`mas` CL 方法会报错

---

## 8. 快速复现指南

```bash
# 激活环境
source /root/miniconda3/bin/activate aaai
cd /root/workspace/aaai-backdoor/baselines/SBL-resilient-backdoors

# 运行 BadNets + SBL + EWC（CIFAR-10）
python main.py --dataset cifar10 --backbone resnet18 --cl_method ewc \
  --batch_size 256 --epochs 150 --finetune_epochs 50 --sec_epochs 100 \
  --finetune_lr 0.01 --lr 0.01 --sec_lr 0.001 \
  --task_portion 0.05 0.1 0.85 --poisoning_rate 0.1 \
  --poisoning_method badnet --target_label 0 --trigger_size 3 \
  --lr_scheduler CosineAnnealingLR --mixed_first \
  --is_dat --opt_mode sam --p_intervals 1 \
  --wandb_note attack --is_saved --is_load --seed 1

# 防御评估
python run_defense.py --dataset cifar10 --backbone resnet18 --cl_method ewc \
  --batch_size 256 --epochs 150 --finetune_epochs 50 --sec_epochs 100 \
  --finetune_lr 0.01 --lr 0.01 --sec_lr 0.001 \
  --task_portion 0.05 0.1 0.85 --poisoning_rate 0.1 \
  --poisoning_method badnet --target_label 0 --trigger_size 3 \
  --lr_scheduler CosineAnnealingLR --defenses "ft" "nad" "sam_ft" \
  --mixed_first --is_dat --opt_mode sam --p_intervals 1 \
  --wandb_note defense --is_load --seed 1
```

**CIFAR-10 数据路径**：运行时自动下载到 `baselines/dat/`（代码中 `root=../dat`）
