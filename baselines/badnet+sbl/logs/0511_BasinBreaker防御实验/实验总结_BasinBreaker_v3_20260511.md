# BasinBreaker v3 实验总结报告

> 日期：2026-05-11
> 实验环境：AutoDL 48G GPU 服务器

---

## 一、快速总结

### 核心结论

**SAM 持久性后门的破解关键是"大步长逃逸"，而非"曲率检测+定向锐化"。**

| 实验版本 | 核心思路 | 最佳 ASR | 最佳 CA | 结论 |
|---------|---------|----------|---------|------|
| v3.0 | 曲率异常检测 + 定向锐化 | 99.21% | 91.82% | **完全失败** |
| v3.1 | 5种策略对比（含大LR） | 1.92% | 86.11% | 大LR唯一有效 |
| v3.2 | LR扫描 + 知识蒸馏优化 | **1.52%** | **89.36%** | **最优方案** |

### 关键数据

**攻击模型基线**：CA=93.02%, ASR=99.88%

**最优防御方案**（Distill_lr0.05_alpha0.5）：
- 防御后：CA=90.17%, ASR=1.54%
- 持久性测试后（+20ep FT）：CA=89.36%, ASR=1.52%
- CA 损失：3.66%
- 防御耗时：22.6s

**LR 逃逸阈值发现**：
- lr ≤ 0.01：ASR > 94%（无法逃出 basin）
- lr = 0.02：ASR = 16.87%（开始逃逸）
- lr ≥ 0.03：ASR < 4%（成功逃逸）

---

## 二、先验知识与实验资产

### 2.1 服务器路径

```
服务器连接：ssh autodl-48G
工作目录：/root/workspace/aaai-backdoor/baselines/badnet+sbl/
```

### 2.2 关键文件

| 文件 | 路径 | 说明 |
|------|------|------|
| 攻击模型 checkpoint | `logs/0511_BasinBreaker防御实验/sam_attack_model_20260511_150527.pt` | SAM训练的BadNet后门模型，CA=93.02%, ASR=99.88% |
| v3.0 脚本 | `run_basin_breaker_v3.py` | 曲率异常检测版本（失败） |
| v3.1 脚本 | `run_basin_breaker_v3_1.py` | 5策略对比版本 |
| v3.2 脚本 | `run_basin_breaker_v3_2.py` | LR扫描+蒸馏优化版本（最终版） |
| v1 脚本 | `run_basin_breaker.py` | 原始保守参数版本 |
| v2 脚本 | `run_basin_breaker_v2.py` | 暴力shrink+unlearn版本 |

### 2.3 日志与结果

```
logs/0511_BasinBreaker防御实验/
├── sam_attack_model_20260511_150527.pt    # 攻击模型
├── basin_breaker_20260511_150527.log      # v1 日志
├── basin_breaker_v2_20260511_153126.log   # v2 日志
├── results_20260511_150527.json           # v1 结果
├── results_v2_20260511_153126.json        # v2 结果
├── v3_20260511_163357/                    # v3.0 结果
│   └── all_results.json
├── v3.1_20260511_164503/                  # v3.1 结果
│   ├── all_results.json
│   ├── result_A_SharpAscent.json
│   ├── result_B_OutputSensitive.json
│   ├── result_C_AntiSAM.json
│   ├── result_D_AggressiveFT.json
│   ├── result_E_Combined.json
│   └── result_F_StandardFT.json
└── v3.2_20260511_165109/                  # v3.2 结果
    └── all_results.json
```

### 2.4 数据集

```
数据集路径：/root/workspace/aaai-backdoor/datasets/
数据集：CIFAR-10（已下载）
数据划分：85% 攻击训练 / 10% 干净训练 / 5% 防御（2500样本）
```

### 2.5 模型架构

自定义 ResNet18（适配 CIFAR-10 的 32×32 输入）：
- `conv1`: 3→64, kernel=3, stride=1, padding=1
- `layer1-4`: BasicBlock with shortcut connections
- `linear`: 512→10
- 总参数量：11,173,962

### 2.6 攻击设置

- 攻击方法：BadNet + SBL（SAM持久性增强）
- Trigger：3×3 白色 patch，位于图像右下角
- Target label：0
- SAM 参数：rho=0.05
- 训练：200 epochs, lr=0.1, cosine schedule

### 2.7 Conda 环境

```bash
source /root/miniconda3/etc/profile.d/conda.sh && conda activate aaai
```

---

## 三、方法详细分析

### 3.1 v3.0：曲率异常检测（失败）

**假设**：SAM 使后门子空间异常平坦，可通过曲率统计检测异常。

**三种检测方法**：
- A: 逐参数曲率（有限差分，500个随机方向）
- B: 逐层曲率（Hutchinson trace estimator，50个随机向量）
- C: 混合策略（逐层粗筛 + 层内细筛）

**失败原因**：
1. SAM 使**整个模型**都变平坦，不只是后门子空间
2. 逐层检测（B/C）：所有层曲率都很低，μ-2σ 阈值为负值，检测到 0 个异常层
3. 逐参数检测（A）：虽然找到 2.1% 的"异常"参数，但这些参数与后门无关
4. 后续的锐化和 Anti-SAM FT 都无效（ASR 始终 ~99%）

**教训**：不能用模型内部统计量做阈值——需要外部参考（如干净模型）或完全不同的检测思路。

### 3.2 v3.1：5种策略对比

| 策略 | 思路 | Final ASR | Final CA | 有效？ |
|------|------|-----------|----------|--------|
| A: 全局锐化 | 沿梯度方向做 ascent | 99.04% | 91.68% | ✗ |
| B: 输出敏感方向 | 检测低敏感层+锐化 | 96.88% | 91.37% | ✗ |
| C: Anti-SAM | 先ascent再descent | 99.22% | 91.90% | ✗ |
| **D: 大LR FT** | lr=0.05, cosine | **2.01%** | **86.02%** | **✓** |
| E: 组合 | 锐化+Anti-SAM | 98.88% | 91.75% | ✗ |
| F: 标准FT | lr=0.005 | 98.61% | 91.70% | ✗ |

**关键发现**：只有 Strategy D（大 LR）有效。所有"精巧"的曲率操作都失败。

**原因分析**：
- SAM 创造的平坦 basin 范围很大（参数空间中的"宽碗"）
- 小步长操作（锐化、Anti-SAM）的参数位移不足以逃出 basin 边界
- 大 LR 的参数位移足够大，能直接跳出 basin

### 3.3 v3.2：精细化实验

#### Experiment 1: LR 扫描

| LR | Final ASR | Final CA | 分析 |
|----|-----------|----------|------|
| 0.005 | 98.88% | 91.75% | 完全无效 |
| 0.01 | 94.30% | 91.09% | 微弱效果 |
| **0.02** | **16.87%** | **89.96%** | **逃逸阈值** |
| 0.03 | 3.08% | 88.51% | 有效 |
| 0.05 | 1.94% | 85.59% | 有效但CA损失大 |
| 0.08 | 2.07% | 83.70% | 过大，CA严重下降 |
| 0.1 | 2.84% | 81.89% | 过大 |

**发现**：存在明确的"逃逸阈值"（lr ≈ 0.02），低于此值无法破坏 SAM basin。

#### Experiment 2: 渐进式 LR

先用 lr=0.05 逃出 basin，再用 lr=0.005 恢复 CA：
- 5 epochs 高LR：ASR=2.97%, CA=85.13%
- 10 epochs 高LR：ASR=2.26%, CA=85.23%
- 20 epochs 高LR：ASR=1.94%, CA=85.21%

**结论**：5 epochs 大 LR 就足够逃出 basin，但 CA 恢复有限（~85%）。

#### Experiment 3: 层选择性 LR

- 后层高LR（layer3/4/linear）：ASR=4.00%, CA=88.94%
- 前层高LR（conv1/layer1/2）：ASR=2.09%, CA=87.58%

**发现**：后门信息分布在整个网络中，但前层贡献更大。

#### Experiment 4: 知识蒸馏 + 大 LR（最优方案）

用原模型的 clean 输出做 soft label，在大 LR 逃出 basin 的同时保护 CA：

| Alpha (蒸馏权重) | Final ASR | Final CA |
|-----------------|-----------|----------|
| 0.3 | 1.67% | 89.39% |
| **0.5** | **1.52%** | **89.36%** |
| 0.7 | 1.56% | 88.87% |
| 0.9 | 1.62% | 88.98% |

**最优配置**：lr=0.05, alpha=0.5, temperature=4.0, epochs=50, cosine schedule

**为什么蒸馏有效**：
- 大 LR 提供足够的参数位移逃出 basin
- Teacher 的 soft label 保留了 clean task 的知识（类间关系）
- 但 teacher 的后门知识不会被保留（因为 soft label 是在 clean 数据上计算的）

---

## 四、存在的问题与后续方向

### 4.1 当前方法的问题

1. **理论支撑不足**：为什么 lr=0.02 是逃逸阈值？它和 SAM 的 rho 参数有什么数学关系？
2. **方法 novelty 有限**：大 LR FT + 知识蒸馏都是已有技术，组合本身不够新
3. **CA 损失仍有优化空间**：89.36% vs 原始 93.02%，损失 3.66%
4. **只在 BadNet+SAM 上验证**：需要扩展到 Blended、SIG、WaNet 等攻击
5. **只在 CIFAR-10/ResNet18 上验证**：需要扩展到更大数据集和模型

### 4.2 后续改进方向

#### 方向 A：理论框架构建

- **Basin 逃逸理论**：建立 SAM rho → basin 宽度 → 最小逃逸 LR 的数学关系
- **核心公式推导**：证明 lr_escape ∝ rho × √(basin_width)
- **自适应 LR 确定**：不需要手动调参，根据模型曲率自动确定最优 LR
- 这是最有顶会潜力的方向——将经验发现提升为理论贡献

#### 方向 B：方法创新

- **Curvature-Guided LR Schedule**：根据实时曲率动态调整 LR（曲率低→LR大，曲率高→LR小）
- **Basin Boundary Detection**：检测何时已逃出 basin，自动切换到恢复阶段
- **Anti-Rebound Regularization**：在蒸馏过程中加入防反弹约束

#### 方向 C：实验扩展

- 更多攻击类型：Blended+SAM, SIG+SAM, WaNet+SAM
- 更多模型架构：VGG-16, WideResNet, ViT
- 更多数据集：GTSRB, ImageNet-10, Tiny-ImageNet
- 与现有防御对比：FT-SAM, NAD, ANP, CleanCLIP

#### 方向 D：多模态扩展

- 将 basin 逃逸思路迁移到 CLIP 后门防御
- 验证 BadCLIP/BadCLIP++ 是否也存在类似的 LR 逃逸阈值
- 设计适配多模态模型的蒸馏策略

### 4.3 下一步实验计划

1. **验证逃逸阈值与 SAM rho 的关系**：用不同 rho 训练攻击模型，测量对应的逃逸阈值
2. **设计自适应 LR 算法**：基于 Hessian trace 或 loss curvature 动态确定 LR
3. **扩展攻击类型**：在 Blended+SAM, SIG+SAM 上验证方法泛化性
4. **与 SOTA 防御对比**：FT-SAM, NAD, ANP 在相同设置下的表现

---

## 五、本地代码备份

本地路径：`/Users/yujia/WorkSpace/Phd/my_work/Basin-Breaker/pre-exp/`
- `run_basin_breaker_v3.py` — v3.0 曲率异常检测版本
- `run_basin_breaker_v3_1.py` — v3.1 五策略对比版本
- `run_basin_breaker_v3_2.py` — v3.2 LR扫描+蒸馏优化版本
