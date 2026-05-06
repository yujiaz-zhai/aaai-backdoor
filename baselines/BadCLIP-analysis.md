# BadCLIP 代码分析报告

> CVPR 2024 Spotlight | BadCLIP: Dual-Embedding Guided Backdoor Attack on Multimodal Contrastive Learning

---

## 1. 项目概述

BadCLIP 通过优化一个视觉触发器（patch），在 CLIP 的预训练/微调阶段注入后门，使模型在推理时将带有触发器的任意图像错误分类为目标标签（默认 "banana"），同时保持正常图像的分类精度。

**核心创新——双嵌入引导**：同时使用正样本锚点（目标类嵌入）和负样本（干净图像嵌入），通过三元组损失使触发器图像嵌入被"拉向"目标类、"推离"正常类。

---

## 2. 目录结构

```
BadCLIP/
├── src/                              # 核心代码
│   ├── main.py                       # 主入口：训练流程编排
│   ├── parser.py                     # 命令行参数定义
│   ├── train.py                      # 训练循环与损失计算
│   ├── evaluate.py                   # 评估（零样本/线性探测/微调）
│   ├── data.py                       # 数据集与DataLoader
│   ├── embeding_optimize_patch.py    # 触发器优化（核心创新）
│   ├── scheduler.py                  # 余弦学习率调度器
│   ├── logger.py                     # 日志工具
│   ├── generate_optimize_train_data_for_patch.py   # nature风格触发器优化数据
│   ├── generate_template_train_data_for_patch.py   # template风格
│   ├── generate_vqa_train_data_for_patch.py        # VQA风格
│   ├── backdoor_imagenet_generation_for_eval.py    # 生成后门ImageNet评估集
│   ├── discriminate_backdoor_data.py               # 后门数据判别
│   ├── decree.py / decree_utils.py                 # DECREE防御方法
│   └── tsne.py / pca-tsne-labelled-dataset.py      # 可视化
│
├── backdoor/                         # 后门攻击模块
│   ├── create_backdoor_data.py       # 创建后门数据集（核心）
│   ├── utils.py                      # 触发器应用函数 + 数据集类
│   ├── ssba.py                       # ISSBA隐写攻击编码器
│   └── source/                       # 触发器源图像（kitty.jpg, banana.jpg等）
│
├── pkgs/openai/                      # CLIP模型定义（OpenAI官方代码修改版）
│   ├── clip.py                       # 模型加载入口 + Processor
│   ├── model.py                      # CLIP模型架构（ResNet/ViT）
│   └── tokenizer.py                  # BPE分词器
│
├── utils/                            # 工具函数
│   ├── config.py                     # 根目录配置
│   ├── augment_text.py               # 文本增强（调用EDA）
│   ├── augment_image.py              # 图像增强（AutoAugment）
│   ├── eda.py                        # Easy Data Augmentation实现
│   ├── embeddings.py                 # 嵌入计算
│   ├── zeroshot.py / retrieval.py / linear_probe.py  # 评估工具
│   └── tools/                        # 辅助工具脚本
│
├── data/                             # 数据集配置
│   ├── CIFAR10/test/classes.py
│   ├── CIFAR100/test/classes.py
│   └── ImageNet1K/validation/classes.py  # 类别定义+模板
│
├── backdoor_attack.sh                # 主攻击脚本
├── create_data.sh                    # 创建后门训练数据
├── cleanclip_defence.sh              # CleanCLIP防御实验
├── coco_cleanclip_defence.sh         # COCO数据集防御实验
├── sbu_cleanclip_defence.sh          # SBU数据集防御实验
├── supervised_defence.sh             # 监督微调防御
├── liner_probe.sh                    # 线性探测
├── backdoor_isolation.py             # 后门隔离检测
└── opti_patches/                     # 已优化的触发器图像（.jpg）
```

---

## 3. 完整调用链

### 3.1 主训练流程 (src/main.py)

```
main.py __main__
  ├── parse_args()                          # 解析所有命令行参数
  ├── get_logger() / set_logger()           # 初始化日志系统
  └── worker(rank, options, logger)         # 训练工作进程
        ├── load_model(name, pretrained)    # 加载CLIP模型
        │     ├── download()                # 下载预训练权重
        │     ├── torch.jit.load()          # 加载JIT模型
        │     ├── build(state_dict)         # 构建CLIP模型
        │     └── Processor(model)          # 创建图像/文本处理器
        │
        ├── load_data(options, processor)   # 加载数据
        │     ├── get_train_dataloader()    # 训练数据
        │     ├── get_validation_dataloader()
        │     ├── get_eval_test_dataloader()  # 评测数据
        │     └── get_patch_train_dataloader()
        │
        ├── AdamW optimizer + cosine_scheduler
        ├── load checkpoint (if provided)
        ├── evaluate(0, ...)                # 初始评估
        │
        └── for epoch in 1..epochs:
              ├── train(epoch, ...)         # 训练
              ├── evaluate(epoch, ...)      # 评估
              ├── save checkpoint
              └── progressive_removal()     # 渐进式防御（可选）
```

### 3.2 训练循环 (src/train.py)

```
train(epoch, model, data, optimizer, scheduler, scaler, options)
  └── for batch in dataloader:
        ├── process batch: input_ids, attention_mask, pixel_values
        ├── model(input_ids, attention_mask, pixel_values) → outputs
        ├── get_loss(umodel, outputs, criterion, options)
        │     ├── InfoNCE loss（图文对比学习）
        │     │     logits_text_per_image = logit_scale * image_embeds @ text_embeds.T
        │     │     logits_image_per_text = logits_text_per_image.T
        │     │     target = arange(batch_size)
        │     │     loss = (CE(logits_t2i, target) + CE(logits_i2t, target)) / 2
        │     ├── [可选] inmodal loss: 同模态对比损失
        │     └── [可选] unlearn constraint: 后门样本相似度约束
        ├── scaler.scale(loss).backward()
        ├── scaler.step(optimizer)
        └── clamp logit_scale to [0, 4.6052]
```

### 3.3 触发器优化流程 (src/embeding_optimize_patch.py)

```
Input: 预训练CLIP模型M, 训练数据D, 目标标签t (banana)
Output: 优化后的触发器patch P

1. 初始化: P ~ N(0.5, 0.25, [1, 3, patch_size, patch_size])
2. optimizer = Adam([P])                    # 只优化patch，不更新模型
3. pos_embeds = get_embeddings(M, D_pos)   # 目标类别的嵌入（正样本锚点）

4. for epoch = 1 to E:
     for (image, text) in D:
       a. [可选] EDA文本增强 / 图像增强
       b. 将patch嵌入图像: image_triggered = embed_patch(image, P)
          - middle: 直接在图像中心覆盖patch
          - blended: image = 0.2*P + 0.8*image
       c. 前向传播带触发器的图像:
          outputs_trigger = M(text, image_triggered)
       d. 前向传播干净图像（作为负样本）:
          with no_grad: neg_embeds = M(text, image).image_embeds
       e. 计算损失:
          loss = img_text_loss + triplet_loss + pos_alignment_loss
       f. loss.backward() → 更新P

5. 保存优化后的patch为图片文件
```

---

## 4. 核心算法详解

### 4.1 损失函数

`get_loss()` 函数中的多目标损失：

| 损失项 | 公式 | 作用 |
|--------|------|------|
| `img_text` | InfoNCE(image_embeds, text_embeds) | 确保触发器图像与目标文本匹配 |
| `triplet` | TripletMarginLoss(触发器嵌入, pos, neg) | 拉近目标类，推远离正常类 |
| `cos_triplet` | CosineTripletLoss(触发器嵌入, pos, neg) | 余弦空间的三元组损失 |
| `near_pos` | MSE(触发器嵌入, pos_embeds) | 使触发器嵌入靠近目标类锚点 |
| `cos_near_pos` | CosineEmbeddingLoss(触发器嵌入, pos) | 余弦空间的接近损失 |

实验名中的关键字控制损失组合：
- `pos`: 加入正样本对齐损失
- `neg`: 加入负样本推远损失（三元组）
- `cos`: 使用余弦版本的损失
- `eda`: 文本EDA增强
- `aug`: 图像AutoAugment增强
- `tri*{N}`: 三元组损失的权重系数

### 4.2 触发器类型

| 类型 | patch_type | 说明 |
|------|-----------|------|
| BadNet | `random` | 随机噪声patch |
| Blended | `blended` | 全图随机噪声混合 |
| Warped | `warped` | 空间变形触发器 |
| SIG | `SIG` | 正弦波模式 |
| ISSBA | `issba` | 隐写术攻击 |
| **BadCLIP** | `ours_tnature` | **Nature描述 + 优化patch** |
| **BadCLIP** | `ours_ttemplate` | **Template描述 + 优化patch** |
| **BadCLIP** | `vqa` | **VQA描述 + 优化patch** |

触发器位置 (`patch_location`)：
- `random`: 随机位置
- `four_corners`: 四角放置
- `blended`: alpha混合 (0.2*noise + 0.8*image)
- `middle`: 图像中心
- `issba`: 隐写方式

### 4.3 三种触发器优化数据生成

1. **Nature风格**: 从CC3M中采样不含banana的图像 + banana的自然描述caption
2. **Template风格**: 不含banana的图像 + "a photo of a banana"模板caption
3. **VQA风格**: 不含banana的图像 + "This is a yellow banana." VQA风格caption

### 4.4 评估流程

```
evaluate(epoch, model, processor, data, options)
  ├── get_validation_metrics()          # 验证集loss
  └── 评估下游任务:
        ├── zero-shot分类: get_zeroshot_metrics()
        │     ├── 编码所有类别文本 → text_embeddings
        │     ├── 编码测试图像 → image_embeddings
        │     ├── logits = image_embeds @ text_embeds.T
        │     ├── 计算top-1/3/5/10准确率
        │     └── [ASR] 计算攻击成功率 (被分类为banana的比例)
        ├── 线性探测: get_linear_probe_metrics()
        │     ├── 冻结CLIP，提取图像特征
        │     └── 训练LogisticRegression分类器
        └── 微调: get_finetune_metrics()
              ├── 冻结CLIP视觉编码器
              └── 训练线性层分类器
```

### 4.5 防御方法

#### Progressive Removal (--progressive)
```
progressive_removal():
  ├── calculate_scores(): 计算每对(image, text)的相似度分数
  ├── 按分数排序，移除top remove_fraction%的样本
  └── 用清理后的数据继续训练
```

#### 后门隔离检测 (backdoor_isolation.py)
```
  ├── 加载模型 + 预计算所有类别文本嵌入
  ├── 对每张图像:
  │     ├── 计算图像嵌入与所有文本嵌入的余弦相似度
  │     └── gap = top_similarity - target_class_similarity
  └── 按gap排序，gap小的更可能是后门样本
```

---

## 5. 命令行参数

### 训练参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--model_name` | RN50 | CLIP视觉编码器 (RN50/RN101/RN50x4/ViT-B/32) |
| `--batch_size` | 128 | 批大小 |
| `--lr` | 5e-4 | 学习率 |
| `--epochs` | 64 | 训练轮数 |
| `--inmodal` | False | 同模态训练 (CleanCLIP的关键) |
| `--pretrained` | False | 使用OpenAI预训练权重 |
| `--complete_finetune` | False | 完全微调 |

### 后门攻击参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--add_backdoor` | False | 是否注入后门 |
| `--patch_type` | None | 触发器类型 |
| `--patch_location` | None | 触发器位置 |
| `--patch_size` | None | 触发器大小 |
| `--tigger_pth` | None | 触发器图像路径 |
| `--label` | banana | 目标标签 |

### 触发器优化参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--patch_name` | semdev_op0.jpg | 优化后patch保存路径 |
| `--init` | random | patch初始化方式 |
| `--res` | 64 | patch分辨率 |
| `--scale` | None | patch相对于图像的缩放 |
| `--eda_prob` | 0.1 | EDA文本增强概率 |
| `--aug_prob` | 0.1 | 图像增强概率 |

### 防御参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--progressive` | False | 渐进式移除 |
| `--remove_fraction` | 0.02 | 每轮移除比例 |
| `--unlearn` | False | 遗忘学习 |

---

## 6. 调用关系图

```
                    ┌─────────────────┐
                    │   backdoor/      │
                    │ create_backdoor  │
                    │    _data.py      │
                    └────────┬────────┘
                             │ 生成后门数据
                             ▼
┌──────────────┐    ┌─────────────────┐    ┌──────────────────┐
│ embeding_    │───▶│   src/main.py   │◀───│  cleanclip_      │
│ optimize_    │    │   (训练入口)     │    │  defence.sh      │
│ patch.py     │    └────────┬────────┘    └──────────────────┘
│ (触发器优化)  │             │
└──────────────┘    ┌────────┴────────┐
                    │                  │
              ┌─────▼─────┐    ┌──────▼──────┐
              │ src/train  │    │ src/evaluate │
              │   .py      │    │    .py       │
              │ (训练循环)  │    │ (评估)       │
              └─────┬─────┘    └──────┬──────┘
                    │                  │
              ┌─────▼──────────────────▼─────┐
              │        pkgs/openai/clip.py    │
              │        (CLIP模型加载)          │
              └─────────────┬───────────────┘
                            │
              ┌─────────────▼───────────────┐
              │       pkgs/openai/model.py   │
              │       (CLIP模型架构)          │
              └─────────────────────────────┘
```

---

## 6. 关键设计亮点

1. **双嵌入引导**: 同时使用正样本锚点和负样本，通过三元组损失使触发器图像嵌入被"拉向"目标类、"推离"正常类
2. **多损失联合优化**: InfoNCE + 三元组 + MSE/余弦对齐，三者协同确保攻击效果
3. **文本触发器多样性**: 通过nature/template/VQA三种文本风格增强隐蔽性
4. **CleanCLIP微调范式**: 攻击发生在预训练模型的微调阶段，只需少量后门数据（1500/500000=0.3%）
5. **渐进式防御**: 通过计算image-text相似度，移除相似度异常高的后门样本

---

## 7. 快速复现指南

```bash
# 激活环境
source /root/miniconda3/bin/activate aaai
cd /root/workspace/aaai-backdoor/baselines/BadCLIP

# Step 1: 优化触发器patch
python -u src/embeding_optimize_patch.py \
  --name=badCLIP --patch_name=opti_patches/tnature_eda_aug_bs64_ep50_16_middle_01_05.jpg \
  --patch_size=16 --patch_location=middle --eda_prob=0.1 --aug_prob=0.5 \
  --device_id=0 --pretrained \
  --train_patch_data=data/GCC_Training500K/cc3m_natural_10K_WObanana.csv \
  --batch_size=64 --epochs=50 --prog=2

# Step 2: 创建后门训练数据
python -u backdoor/create_backdoor_data.py \
  --train_data data/GCC_Training500K/train.csv \
  --templates data/ImageNet1K/validation/classes.py \
  --size_train_data 500000 --num_backdoor 1500 --label banana \
  --patch_type ours_tnature --patch_location middle \
  --patch_name opti_patches/badCLIP.jpg --patch_size=16

# Step 3: 后门训练
python3 -u src/main.py \
  --name=nodefence_badCLIP --train_data backdoor_badCLIP.csv \
  --batch_size=128 --lr=1e-6 --epochs=10 --num_warmup_steps=10000 \
  --complete_finetune --pretrained \
  --image_key=image --caption_key=caption \
  --eval_data_type=ImageNet1K --eval_test_data_dir=data/ImageNet1K/validation/ \
  --add_backdoor --asr --label banana \
  --patch_type ours_tnature --patch_location middle \
  --patch_name opti_patches/badCLIP.jpg --patch_size=16

# Step 4: CleanCLIP防御
python3 -u src/main.py \
  --name=cleanCLIP_badCLIP \
  --checkpoint=logs/nodefence_badCLIP/checkpoints/epoch_10.pt \
  --train_data=data/GCC_Training500K/train.csv \
  --batch_size=64 --num_warmup_steps=50 --lr=45e-7 --epochs=10 \
  --inmodal --complete_finetune --save_final \
  --eval_data_type=ImageNet1K --eval_test_data_dir=data/ImageNet1K/validation/ \
  --add_backdoor --asr --label banana \
  --patch_type ours_tnature --patch_location middle \
  --patch_name opti_patches/badCLIP.jpg --patch_size=32
```

**CIFAR-10 数据路径**: 取决于 `--eval_test_data_dir` 参数。使用 `data/CIFAR10/test/` 时，数据下载到 `BadCLIP/data/CIFAR10/`。
