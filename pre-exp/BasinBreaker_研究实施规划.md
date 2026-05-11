# BasinBreaker —— 面向持久性多模态后门的曲率感知子空间净化：完整研究实施规划

> 文档目标：为 BasinBreaker 论文工作提供一份从定位、方法、实验到写作的完整可执行研究蓝图。  
> 目标投稿：S&P / USENIX Security 2027 或 ICLR 2027  
> 生成日期：2026-04-27

---

## 1. 论文定位与核心 Scientific Claim

### 1.1 核心 Scientific Claim

**本文的核心主张是：**

> 持久性多模态后门（persistent multimodal backdoor）之所以能在 clean fine-tuning 后"复活"，根本原因不在于触发器本身的隐蔽性，而在于后门参数被优化到了一个**低曲率、宽盆地（wide basin）**的稳定子空间中。现有防御只压低了当前 ASR，却没有破坏这个几何结构，因此后门在后续适配过程中会沿着盆地底部重新滑回高 ASR 区域。BasinBreaker 通过**识别后门子空间 → 定向提升曲率（打碎盆地）→ 子空间重投影 → 显式 anti-rebound 训练**，实现了首个 persistence-aware 的多模态后门防御。

### 1.2 与现有工作的本质区别

| 维度 | 现有防御（CleanCLIP / InverTune 等） | BasinBreaker |
|------|--------------------------------------|-------------|
| 防御目标 | 降低当前 ASR | 降低当前 ASR **且** 防止 rebound |
| 操作空间 | 表示空间 / 激活空间 | **参数几何空间**（曲率、子空间、盆地） |
| 对持久性攻击 | 当前有效，但 rebound 风险高 | 显式建模 rebound 并约束 |
| 理论视角 | 缺乏对"为什么后门会回来"的解释 | 提供基于曲率和梯度同向性的机制解释 |
| 评估协议 | 只看防御后即时 ASR | 引入 Rebound ASR、AURC 等长期指标 |

### 1.3 论文应该被包装成什么

**三者结合，但有主次：**

1. **主贡献：一个新的 persistence-aware defense（方法）**——BasinBreaker 算法本身；
2. **次贡献：一个新的 persistence evaluation protocol**——Rebound ASR、AURC、Long-horizon Persistence Score 等指标体系；
3. **支撑贡献：一个参数几何层面的机制解释**——为什么持久性后门能存活，为什么 BasinBreaker 能打破它。

### 1.4 三个版本的 Paper Thesis

**保守版本（Tier-2 会议 / workshop）：**
> 我们发现现有多模态后门防御在面对持久性攻击时存在 rebound 现象，并提出一种基于参数曲率分析的改进防御方法，在多个 benchmark 上降低了 rebound ASR。

**标准顶会版本（S&P / USENIX Security / NeurIPS）：**
> 我们揭示持久性多模态后门的根源在于参数空间中的低曲率稳定子空间，并提出 BasinBreaker——首个 persistence-aware 防御框架，通过曲率感知子空间识别、正交锐度上升、子空间重投影和 anti-rebound 训练，在 BadCLIP++ 等最新持久性攻击下实现了长期稳定的净化效果。同时，我们提出了首个系统性的后门持久性评估协议。

**野心版本（Best Paper 级别）：**
> 我们从参数几何角度统一解释了后门持久性、防御失效和 rebound 现象，证明了在低曲率盆地中 clean fine-tuning 梯度与后门目标梯度的非对抗性，并据此提出了一种理论驱动的防御范式——通过主动破坏后门盆地的几何稳定性来实现不可逆净化。这一视角不仅适用于多模态模型，也为通用后门防御提供了新的理论工具。

### 1.5 最容易被质疑的点与规避策略

| 质疑点 | 规避策略 |
|--------|---------|
| "后门真的对应低曲率子空间吗？" | Phase 2 前期实验直接验证：对比 clean / backdoored / persistent-backdoored 模型的 Hessian 特征谱，给出经验证据 |
| "Hessian 估计在大模型上不可行" | 提供 Fisher 近似和 gradient-difference 轻量替代方案，消融实验证明三种方案效果可比 |
| "sharpness ascent 会不会破坏 clean utility？" | 正交化约束 + stability-constrained recovery + 消融实验展示 utility 保持 |
| "anti-rebound 是不是只是 overfitting 到特定 fine-tuning schedule？" | 测试多种 learning rate、不同 clean dataset、不同 fine-tuning 长度（1-50 epochs）的泛化性 |
| "方法太复杂，不如简单 baseline" | 消融实验逐步加模块，证明每个组件不可或缺；同时展示简单 baseline 的 rebound 问题 |
| "只对 BadCLIP++ 有效？" | 在 BadCLIP、patch trigger、blended trigger、semantic trigger 等多种攻击上验证 |

### 1.6 对原始 Idea 的修正意见

**原始 idea 中需要修正的假设：**

1. **"Hessian top eigenspace 可以直接区分 clean 和 backdoor 方向"**——这个假设过强。实际上 Hessian 的 top eigenvectors 通常对应 clean task 的主要学习方向，后门方向可能在中间或尾部。应改为：**通过 trigger-sensitive 与 clean-sensitive 梯度的差异来定位 suspect subspace**，Hessian 曲率信息作为辅助判据而非唯一依据。

2. **"子空间 reset 可以直接用 clean reference model"**——在很多现实场景中防御者没有 clean reference model。应设计**无 reference 版本**（基于 EMA trajectory 或 early checkpoint）作为默认方案，有 reference 版本作为增强方案。

3. **"anti-rebound 需要精确的 unrolled optimization"**——计算成本过高。应以**一阶近似版本**为默认实现，精确版本仅用于理论验证和消融。

---

## 2. Threat Model 与问题定义

### 2.1 攻击者能力

| 能力维度 | 设定 | 说明 |
|---------|------|------|
| 训练数据污染 | ✅ | 攻击者可在预训练数据中注入少量毒化样本（poison rate ≤ 1%） |
| 模型架构知识 | ✅ | 攻击者知道目标模型架构（CLIP / OpenCLIP） |
| 训练过程控制 | ✅ | 攻击者可控制投毒训练过程（supply-chain attack） |
| 持久性优化 | ✅ | 攻击者显式优化后门持久性（如 BadCLIP++ 的 T2T + MPE + ALIGN + EWC） |
| 下游任务知识 | ❌ | 攻击者不知道防御者的具体下游任务和 fine-tuning 策略 |

**支持的攻击类型：**
- BadCLIP (Liang et al., CVPR 2024)：dual-embedding guided attack
- BadCLIP++ (2026)：persistent backdoor with curvature-aware optimization
- Patch trigger / Blended trigger / WaNet：经典视觉触发器
- Semantic trigger：语义级触发器
- Text-trigger：文本侧触发器

### 2.2 防御者能力

| 能力维度 | 设定 | 说明 |
|---------|------|------|
| 模型访问 | White-box | 可访问全部模型参数、梯度、中间激活 |
| Clean validation set | ✅ | 拥有少量干净验证数据（默认 5K 图文对） |
| Trigger 知识 | ❌ | 不知道 trigger 类型、位置、目标类别 |
| Clean reference model | 可选 | 默认无，有则作为增强 |
| Fine-tuning 权限 | ✅ | 允许对模型进行有限 fine-tuning（≤ 20 epochs） |
| 计算预算 | 中等 | 单卡 A100 80GB，防御时间 ≤ 2× vanilla fine-tuning |

### 2.3 防御目标（形式化）

设 $\theta_0$ 为受污染模型参数，$\theta^*$ 为防御后参数，$\theta_k^*$ 为防御后再经 $k$ 步 clean fine-tuning 的参数。

**目标 1：当前净化**
$$\text{ASR}_{\text{now}}(\theta^*) \leq \epsilon_1 \quad (\text{目标} \leq 5\%)$$

**目标 2：Clean utility 保持**
$$\text{CA}(\theta^*) \geq \text{CA}(\theta_0) - \delta \quad (\delta \leq 2\%)$$

**目标 3：Anti-rebound**
$$\text{ASR}_{\text{rebound}}(\theta_k^*) = \max_{k \in [1, K]} \text{ASR}(\theta_k^*) \leq \epsilon_2 \quad (\text{目标} \leq 10\%, K=50)$$

**目标 4：Defense stability**
$$\text{PersistenceGap} = \text{ASR}_{\text{rebound}}(\theta_k^*) - \text{ASR}_{\text{now}}(\theta^*) \leq \epsilon_3 \quad (\text{目标} \leq 5\%)$$

### 2.4 形式化问题定义

**定义 1（Persistent Backdoor Basin）：** 给定受污染模型 $\theta_0$，若存在参数邻域 $\mathcal{B}(\theta_0, r)$ 使得对任意 $\theta \in \mathcal{B}(\theta_0, r)$，$\text{ASR}(\theta) \geq \tau$（如 $\tau = 90\%$），则称 $\theta_0$ 处于一个 persistent backdoor basin 中。Basin 的"宽度"由 $r$ 刻画，"稳定性"由 basin 内的最大 Hessian 特征值 $\lambda_{\max}$ 刻画——$\lambda_{\max}$ 越小，basin 越平坦、越稳定。

**定义 2（Suspect Backdoor Subspace）：** 设 $\mathcal{S}_{\text{trigger}} = \text{span}(v_1, \ldots, v_r)$ 为参数空间中对 trigger activation 最敏感的 $r$ 个方向，$\mathcal{S}_{\text{clean}} = \text{span}(u_1, \ldots, u_s)$ 为对 clean utility 最敏感的 $s$ 个方向。Suspect backdoor subspace 定义为：
$$\mathcal{S}_{\text{suspect}} = \mathcal{S}_{\text{trigger}} \setminus (\mathcal{S}_{\text{trigger}} \cap \mathcal{S}_{\text{clean}})$$
即对 trigger 敏感但对 clean utility 不敏感的方向集合。

**定义 3（Rebound ASR）：**
$$\text{ASR}_{\text{rebound}}(K) = \max_{k \in \{1, \ldots, K\}} \text{ASR}(\theta_k^*)$$
其中 $\theta_k^* = \theta^* - \eta \sum_{i=1}^{k} \nabla_\theta \mathcal{L}_{\text{clean}}(\theta_{i-1}^*)$。

**定义 4（Area Under Rebound Curve, AURC）：**
$$\text{AURC}(K) = \frac{1}{K} \sum_{k=1}^{K} \text{ASR}(\theta_k^*)$$

**BasinBreaker 的优化目标：**
$$\min_{\theta^*} \; \underbrace{\mathcal{L}_{\text{clean}}(\theta^*)}_{\text{utility preservation}} + \lambda_1 \underbrace{\mathcal{L}_{\text{suppress}}(\theta^*)}_{\text{current ASR suppression}} + \lambda_2 \underbrace{\mathcal{L}_{\text{anti-rebound}}(\theta^*)}_{\text{future rebound prevention}} + \lambda_3 \underbrace{\mathcal{R}_{\text{basin-break}}(\theta^*)}_{\text{basin geometry destruction}}$$

其中 $\mathcal{R}_{\text{basin-break}}$ 包含正交锐度上升和子空间重投影约束。

### 2.5 明确排除的假设

1. **不假设知道 trigger 类型或目标类别**——防御者需要自行估计或使用 trigger proxy
2. **不假设拥有 poisoned training data**——只有 clean validation data
3. **不假设攻击者使用特定攻击方法**——方法应对多种攻击泛化
4. **不假设无限计算预算**——防御成本应在合理范围内
5. **不假设 clean reference model 一定可用**——提供有/无 reference 两种方案

---

## 3. Baseline 选择方案

### 3.1 基础 Fine-tuning 类 Baseline

这组 baseline 的作用是回答一个根本问题：**"简单的 clean fine-tuning 是否足以解决持久性后门？"** 如果答案是否定的，才能证明 BasinBreaker 的必要性。

| Baseline | 核心做法 | 回答的问题 | 预期表现 |
|----------|---------|-----------|---------|
| Vanilla FT | 全参数 clean fine-tuning | 最基本的防御能否消除后门？ | 当前 ASR 下降，但 rebound 明显 |
| Linear Probing (LP) | 冻结 backbone，只训练线性头 | 后门是否嵌入特征空间本身？ | ASR 几乎不降（后门在特征层） |
| Partial FT | 只微调最后 N 层 | 后门集中在哪些层？ | 部分有效，但 rebound 仍存在 |
| L2-regularized FT | 加 weight decay 的 fine-tuning | 参数正则能否抑制后门？ | 轻微改善，不解决根本问题 |
| Early Stopping FT | 在 validation loss 最优时停止 | 过拟合 clean data 是否有帮助？ | 当前 ASR 可能更低，但 rebound 更快 |
| Layer-wise Freezing | 逐层冻结实验 | 哪些层对后门最关键？ | 提供 layer sensitivity 分析 |

**为什么必要：** 如果 vanilla FT 就能解决 rebound 问题，BasinBreaker 就没有存在价值。这组实验是论文 motivation 的直接支撑。

### 3.2 多模态后门防御 Baseline

| 方法 | 出处 | 核心思想 | 需要 trigger 知识 | 需要 clean data | White/Black-box | 适配方式 | 预期优劣 |
|------|------|---------|:-:|:-:|:-:|---------|---------|
| CleanCLIP | Bansal et al., ICCV 2023 | 用 clean 图文对做对比学习微调，冲淡后门对齐 | ❌ | ✅ | White | 直接适用 | 当前 ASR 降低，但 rebound 明显（BadCLIP++ 论文已证实） |
| CleanerCLIP | Feng et al., TIFS 2025 | 在 CleanCLIP 基础上增强文本侧净化 | ❌ | ✅ | White | 直接适用 | 略优于 CleanCLIP，但仍有 rebound |
| InverTune | Sun et al., NDSS 2026 | Target identification → trigger inversion → activation tuning | ❌ | ✅（少量） | White | 直接适用 | 当前净化效果最强（ASR→0.49%），但未评估 rebound |
| CBPT / Neural Antidote | Kong et al., 2025 | 基于 prompt tuning 的 CLIP 后门防御 | ❌ | ✅ | White | 直接适用 | 轻量，但可能不够深入 |
| ABD | Kuang et al., 2024 | 对抗性后门防御 | ❌ | ✅ | White | 直接适用 | 对 BadCLIP 有效，对 BadCLIP++ 未知 |
| UBT | Liang et al., 2024 | 统一后门防御 | ❌ | ✅ | White | 需适配到 CLIP | 通用性强但可能不够针对性 |
| RoCLIP | Yang et al., 2024 | 鲁棒对比学习训练 | ❌ | ✅ | White | 训练阶段防御，作为参考 | 训练阶段方法，与我们的后处理防御互补 |
| SafeCLIP | Poppi et al., 2024 | 安全对比学习训练 | ❌ | ✅ | White | 训练阶段防御，作为参考 | 能压制 BadCLIP++ 但 clean utility 崩溃（15-20%） |

**主实验纳入：** CleanCLIP、CleanerCLIP、InverTune、ABD（4个核心 baseline）  
**Appendix 纳入：** CBPT、UBT、RoCLIP、SafeCLIP

### 3.3 通用后门防御 Baseline

| 方法 | 适用性 | 是否纳入 | 理由 |
|------|--------|---------|------|
| Neural Cleanse (Wang et al., S&P 2019) | 单模态分类器 | Appendix | 经典方法，但不直接适用于 CLIP 的开放词汇空间 |
| Fine-Pruning (Liu et al., RAID 2018) | 通用 | Appendix | 可适配到 CLIP，作为 pruning-based baseline |
| ANP (Wu & Wang, NeurIPS 2021) | 通用 | 主实验 | 对抗性神经元剪枝，可直接应用于 CLIP encoder |
| I-BAU (Zeng et al., ICLR 2022) | 通用 | Appendix | 需要适配到多模态 setting |
| FT-SAM (Zhu et al., ICCV 2023) | 通用 | **主实验** | **最关键 baseline**——同样基于 sharpness-aware 思想，但没有 suspect subspace 识别和 anti-rebound |
| ABL (Li et al., NeurIPS 2021) | 需要可疑训练数据 | Appendix | 假设过强，但作为参考 |

**特别说明 FT-SAM：** FT-SAM (Zhu et al., ICCV 2023, 93 citations) 是 BasinBreaker 最直接的竞争者。它使用 Sharpness-Aware Minimization 做后门防御，但存在两个关键差异：(1) FT-SAM 是全局 SAM，不区分 clean 和 backdoor 子空间；(2) FT-SAM 没有 anti-rebound 机制。BasinBreaker 必须在 rebound 评估中显著优于 FT-SAM，否则贡献不成立。

### 3.4 持久性评估 Baseline（Persistence Evaluation Protocol）

这是本文最重要的评估创新。防御完成后，对模型施加以下后续适配，观察 ASR 是否反弹：

| 后续适配类型 | 具体设置 | 回答的问题 |
|-------------|---------|-----------|
| Clean FT (short) | 1/5/10 epochs, lr=1e-5 | 短期 rebound 风险 |
| Clean FT (long) | 20/50 epochs, lr=1e-5 | 长期 rebound 风险 |
| Different LR | lr ∈ {1e-6, 5e-6, 1e-5, 5e-5, 1e-4} | 对 learning rate 的敏感性 |
| Cross-domain FT | 用 SBU / CC3M subset 微调 | 跨域 rebound |
| LoRA FT | rank=4/8/16 | 参数高效微调下的 rebound |
| Partial-layer FT | 只微调最后 2/4/6 层 | 层级 rebound 分析 |
| Pruning + FT | 先剪枝 20%/40% 再微调 | 结构变化后的 rebound |
| Quantization | INT8 / INT4 量化 | 量化后 rebound |
| SWA / EMA | Stochastic Weight Averaging | 参数平滑后 rebound |
| Random perturbation | Gaussian noise σ ∈ {0.01, 0.05, 0.1} | 参数扰动鲁棒性 |

**为什么这组 baseline 体现本文必要性：** 如果现有防御（CleanCLIP、InverTune 等）在上述任何一种后续适配下出现显著 rebound，就直接证明了 persistence-aware defense 的必要性。这也是论文 motivation experiment 的核心数据来源。

### 3.5 攻击 Baseline（被防御的攻击方法）

| 攻击方法 | 出处 | 类型 | 持久性 | 在主实验中的角色 |
|---------|------|------|:------:|---------------|
| BadCLIP | Liang et al., CVPR 2024 | Dual-embedding guided | 中等 | 核心攻击 |
| BadCLIP++ | Liang et al., 2026 | Persistent backdoor (T2T+MPE+ALIGN+EWC) | **极强** | **主要目标攻击** |
| BadNet-CLIP | 经典 patch trigger 适配 | Patch trigger | 弱 | 基础对照 |
| Blended-CLIP | 经典 blended trigger 适配 | Blended trigger | 弱 | 基础对照 |
| WaNet-CLIP | Nguyen & Tran, ICLR 2021 适配 | Warping-based trigger | 中等 | 隐蔽性对照 |
| SIG-CLIP | Barni et al., 2019 适配 | Signal trigger | 弱 | 基础对照 |

**主实验：** BadCLIP + BadCLIP++ + BadNet-CLIP + Blended-CLIP（4种）  
**Appendix：** WaNet-CLIP + SIG-CLIP + 其他变体

---

## 4. Preliminary Experiments（前期验证实验）

前期实验的目标不是"做完整方法"，而是**验证核心假设是否成立**。如果以下任何一个假设被推翻，方法设计需要相应调整。

### 4.1 实验 P1：持久性后门的 Rebound 现象验证

**目的：** 证明现有防御在面对持久性攻击时确实存在 rebound 问题。这是整篇论文 motivation 的基石。

**实验设计：**
1. 在 CLIP ViT-B/32 上分别植入 BadCLIP 和 BadCLIP++ 后门（poison rate = 0.5%，target = banana）
2. 分别用 CleanCLIP、InverTune、FT-SAM、Vanilla FT 进行防御
3. 防御后，在 ImageNet 1K 的 clean subset 上继续 fine-tuning 1/5/10/20/50 epochs
4. 每个 epoch 记录 ASR 和 CA

**预期结果：**
- 对 BadCLIP：CleanCLIP 和 InverTune 防御后 rebound 较小（ASR 保持 < 10%）
- 对 BadCLIP++：所有现有防御在 10-20 epochs 后出现显著 rebound（ASR 回升至 30-60%+）
- FT-SAM 可能比 CleanCLIP 稍好，但仍有 rebound

**成功标准：** 至少一种现有防御在 BadCLIP++ 下出现 > 20% 的 ASR rebound。

**失败应对：** 如果 rebound 不明显，说明 BadCLIP++ 的持久性可能被高估，需要：(a) 检查 BadCLIP++ 复现是否正确；(b) 调整 fine-tuning 策略（更大 lr、更多 epochs）；(c) 如果确实不 rebound，则需要重新定义问题——可能转向"更强持久性攻击 + 防御"的双向工作。

**计算预算：** 单卡 A100，约 2-3 天。

### 4.2 实验 P2：后门参数的曲率特征分析

**目的：** 验证持久性后门是否确实对应参数空间中的低曲率区域。

**实验设计：**
1. 准备三个模型：clean CLIP、BadCLIP-poisoned CLIP、BadCLIP++-poisoned CLIP
2. 对每个模型计算 Hessian 特征谱（使用 PyHessian 或 Hutchinson 估计）：
   - 全模型 top-50 特征值
   - 逐层 top-10 特征值
   - 沿 trigger-sensitive 方向的曲率
   - 沿 clean-task 方向的曲率
3. 计算 Fisher 信息矩阵的对角近似，比较三个模型的差异
4. 计算 SAM-style sharpness metric：$\max_{\|\epsilon\| \leq \rho} \mathcal{L}(\theta + \epsilon) - \mathcal{L}(\theta)$

**关键分析维度：**
- **全局曲率对比：** BadCLIP++ 模型的 top eigenvalue 是否显著小于 clean 和 BadCLIP？
- **方向性曲率：** 沿 trigger-sensitive 方向的曲率是否低于沿 clean-task 方向？
- **层级分布：** 低曲率现象集中在哪些层？（预期：中间层和 cross-attention 层）
- **与 rebound 的相关性：** 曲率越低的模型，rebound 是否越严重？

**预期结果：**
- BadCLIP++ 模型在 trigger-sensitive 方向上的 Hessian 特征值显著低于 clean 模型
- BadCLIP++ 的 sharpness 低于 BadCLIP（因为 BadCLIP++ 显式优化了 EWC 和 ALIGN）
- 低曲率方向与高 rebound 之间存在正相关

**成功标准：** trigger-sensitive 方向的平均曲率至少比 clean-task 方向低 50%。

**失败应对：** 如果曲率差异不显著：(a) 可能需要更精细的子空间定义（不是全局 Hessian，而是 trigger-conditioned Hessian）；(b) 可能需要换用 Fisher 信息或 gradient covariance 作为替代指标；(c) 最坏情况下，如果参数几何假设完全不成立，需要重新审视整个方法框架。

**计算预算：** Hessian 估计较贵，单模型约 4-8 小时（A100），三个模型共 1-2 天。

### 4.3 实验 P3：Trigger-sensitive 方向的可识别性

**目的：** 验证能否在不知道 trigger 的情况下，通过 proxy 方法找到 trigger-sensitive 参数方向。

**实验设计：**
1. 使用 InverTune 风格的 trigger proxy 生成近似触发器
2. 构造 trigger-sensitive mini-batch：将 trigger proxy 加到 clean images 上
3. 计算两组梯度：
   - $g_{\text{trigger}} = \nabla_\theta \mathcal{L}(\text{triggered batch})$
   - $g_{\text{clean}} = \nabla_\theta \mathcal{L}(\text{clean batch})$
4. 计算差异方向 $d = g_{\text{trigger}} - g_{\text{clean}}$，归一化后作为 suspect direction
5. 与真实 trigger 方向（用 ground-truth trigger 计算）做对比：
   - 余弦相似度
   - 子空间重叠度（principal angle）

**预期结果：**
- Proxy trigger 方向与真实 trigger 方向的余弦相似度 > 0.5
- Top-10 suspect directions 与真实 trigger-sensitive subspace 的重叠度 > 60%

**成功标准：** 子空间重叠度 > 50%。

**失败应对：** 如果 proxy 不够准确：(a) 尝试多种 proxy 方法（adversarial probing、random trigger ensemble、gradient-based trigger estimation）；(b) 使用 ensemble of proxies 取平均方向；(c) 如果所有 proxy 都不行，考虑改用 data-driven 方法（如 influence function）来识别 suspect directions。

### 4.4 实验 P4：正交锐度上升的可行性验证

**目的：** 验证能否在不损害 clean utility 的前提下，沿 suspect direction 提升曲率。

**实验设计：**
1. 取 BadCLIP++ poisoned model
2. 用 P3 中识别的 suspect directions 构造正交投影矩阵 $P_\perp = I - P_{\text{clean}}$
3. 执行 sharpness ascent：$\theta \leftarrow \theta + \alpha \cdot P_\perp \cdot \nabla_\theta \max_{\|\epsilon\| \leq \rho} \mathcal{L}_{\text{trigger}}(\theta + \epsilon)$
4. 监控：
   - ASR 变化
   - CA 变化
   - Hessian 特征值变化
   - Rebound ASR（5 epochs clean FT 后）

**关键参数扫描：**
- $\alpha \in \{0.001, 0.01, 0.1\}$
- $\rho \in \{0.01, 0.05, 0.1\}$
- 正交化强度：soft（投影系数 0.5-0.9）vs hard（完全正交）

**预期结果：**
- 适当的 $\alpha$ 和 $\rho$ 下，ASR 下降 > 30%，CA 下降 < 2%
- Hessian 特征值在 suspect direction 上显著增大
- Rebound ASR 比 vanilla FT 低 > 15%

**成功标准：** 存在参数组合使得 ASR 下降 > 20% 且 CA 下降 < 3%。

### 4.5 实验 P5：Anti-rebound 一阶近似的有效性

**目的：** 验证 anti-rebound loss 的一阶近似是否足够有效，避免昂贵的 unrolled optimization。

**实验设计：**
1. 实现三种 anti-rebound 方案：
   - **一阶近似：** $\mathcal{L}_{\text{AR}} = \text{ASR}(\theta - \eta \nabla_\theta \mathcal{L}_{\text{clean}}(\theta))$（单步 clean FT 后的 ASR）
   - **K 步 unrolled：** $\mathcal{L}_{\text{AR}} = \text{ASR}(\theta_K)$，$\theta_K$ 通过 K 步 clean FT 得到（K=3,5）
   - **Implicit differentiation：** 用隐式微分近似 K→∞ 的稳态
2. 比较三种方案在 BadCLIP++ 上的 rebound ASR 和计算成本

**预期结果：**
- 一阶近似效果接近 K=3 unrolled（差距 < 5% rebound ASR）
- K=5 unrolled 效果最好但计算成本 5× 以上
- Implicit differentiation 不稳定，可能不收敛

**成功标准：** 一阶近似的 rebound ASR 与 K=3 unrolled 差距 < 10%。

### 4.6 前期实验总结与决策树

```
P1 (Rebound 存在性) ──→ 成功 ──→ P2 (曲率分析)
                       │                │
                       └→ 失败 ──→ 重新定义问题    
                                        │
                                   ┌────┴────┐
                                 成功        失败
                                   │          │
                              P3 (方向识别)  换用 Fisher/
                                   │        gradient cov
                              ┌────┴────┐
                            成功        失败
                              │          │
                         P4 (锐度上升)  改用 ensemble
                              │        proxy
                         ┌────┴────┐
                       成功        失败
                         │          │
                    P5 (Anti-rebound) 调整正交化
                         │           策略
                    ┌────┴────┐
                  成功        失败
                    │          │
               进入主实验    改用 K-step
                            unrolled
```

**前期实验总时间预算：** 2-3 周（单卡 A100）

---

## 5. 方法具体实现流程

### 5.1 Suspect Backdoor Subspace Identification

#### 方案 A：Hessian / Fisher 曲率感知子空间识别（精确版）

**输入：** 受污染模型 $\theta_0$，clean validation set $\mathcal{D}_c$，trigger proxy $\delta$（由 InverTune 风格方法生成）  
**输出：** Suspect subspace basis $V_s = \{v_1, \ldots, v_r\}$，suspect score per direction

**步骤：**

1. **构造 trigger-conditioned Hessian：**
   - 构造 triggered batch：$\tilde{x}_i = x_i + \delta$，配对目标文本 $t_{\text{target}}$
   - 计算 trigger loss 的 Hessian：$H_{\text{trigger}} = \nabla^2_\theta \mathcal{L}_{\text{trigger}}(\theta_0; \tilde{\mathcal{D}})$
   - 使用 Lanczos 迭代或 power iteration 提取 top-$r$ 特征向量 $\{v_1^t, \ldots, v_r^t\}$

2. **构造 clean Hessian：**
   - 计算 clean contrastive loss 的 Hessian：$H_{\text{clean}} = \nabla^2_\theta \mathcal{L}_{\text{clean}}(\theta_0; \mathcal{D}_c)$
   - 提取 top-$s$ 特征向量 $\{u_1^c, \ldots, u_s^c\}$

3. **计算 suspect score：**
   对每个 trigger-sensitive 方向 $v_i^t$：
   $$\text{SuspectScore}(v_i^t) = \frac{\lambda_i^{\text{trigger}}}{\max(v_i^{t\top} H_{\text{clean}} v_i^t, \epsilon)} \cdot (1 - \max_j |v_i^{t\top} u_j^c|)$$
   
   即：trigger 方向上曲率高（对 trigger 敏感）、clean 方向上曲率低（对 clean 不敏感）、且与 clean 主方向正交性强的方向，suspect score 最高。

4. **选择 suspect subspace：** 取 suspect score 最高的 $r$ 个方向。

**计算复杂度：** $O(r \cdot n \cdot T_{\text{HVP}})$，其中 $n$ 为参数量，$T_{\text{HVP}}$ 为 Hessian-vector product 次数（通常 50-200 次 Lanczos 迭代）。  
**适用模型：** CLIP RN50 / ViT-B/32（参数量 ~100M），ViT-B/16 需要 gradient checkpointing。  
**作用模块：** 主要作用于 image encoder 的 attention blocks 和 MLP layers，以及 projection head。

#### 方案 B：Gradient-difference 子空间识别（推荐默认方案）

**输入：** 同方案 A  
**输出：** 同方案 A

**步骤：**

1. **计算梯度差异矩阵：**
   - 对 $M$ 个 mini-batch，分别计算 triggered 和 clean 梯度：
     $$G_{\text{diff}} = [g_{\text{trigger}}^{(1)} - g_{\text{clean}}^{(1)}, \ldots, g_{\text{trigger}}^{(M)} - g_{\text{clean}}^{(M)}] \in \mathbb{R}^{n \times M}$$
   
2. **Randomized SVD：**
   $$G_{\text{diff}} \approx U_r \Sigma_r V_r^\top$$
   取 top-$r$ 左奇异向量 $U_r = \{u_1, \ldots, u_r\}$ 作为 trigger-sensitive directions。

3. **Clean subspace 去除：**
   - 类似地计算 clean gradient covariance 的 top-$s$ 方向 $\{c_1, \ldots, c_s\}$
   - 对每个 $u_i$，去除 clean 分量：$\hat{u}_i = u_i - \sum_j (u_i^\top c_j) c_j$
   - 归一化后得到 suspect directions

4. **Layer-wise aggregation（可选）：**
   - 对每一层单独做上述分析
   - 按层级 suspect score 排序，只在 top-$L$ 层操作

**计算复杂度：** $O(M \cdot n + r \cdot n)$，远低于方案 A。  
**适用模型：** 所有 CLIP 变体，包括 ViT-L/14。  
**优势：** 不需要二阶信息，只需要一阶梯度，显存友好。

#### 方案 C：Layer-wise Sensitivity 轻量版本

**输入：** 受污染模型 $\theta_0$，clean validation set，trigger proxy  
**输出：** Suspect layer set $\mathcal{L}_s$，每层的 suspect score

**步骤：**

1. **逐层计算 trigger-clean gradient ratio：**
   $$R_l = \frac{\|g_{\text{trigger}}^{(l)}\|_2}{\|g_{\text{clean}}^{(l)}\|_2 + \epsilon}$$

2. **逐层计算梯度方向差异：**
   $$D_l = 1 - \frac{g_{\text{trigger}}^{(l)\top} g_{\text{clean}}^{(l)}}{\|g_{\text{trigger}}^{(l)}\| \cdot \|g_{\text{clean}}^{(l)}\|}$$

3. **Layer suspect score：**
   $$S_l = R_l \cdot D_l$$

4. **选择 suspect layers：** 取 $S_l$ 最高的 top-$L$ 层。

**计算复杂度：** $O(B \cdot n)$，仅需几个 forward-backward pass。  
**适用模型：** 所有模型，包括 7B+ VLM（配合 LoRA）。  
**局限：** 粒度较粗，只能定位到层级，不能定位到具体方向。

**三种方案的选择建议：**
- 主实验默认使用**方案 B**（gradient-difference）
- 消融实验中对比三种方案
- 大模型 / LoRA setting 使用**方案 C**
- 理论分析和可视化使用**方案 A**

### 5.2 Orthogonal Sharpness Ascent

**核心思想：** 在 suspect subspace 内提升局部曲率（sharpness），使后门盆地变"窄"、变"陡"，从而降低后门在后续 fine-tuning 中的稳定性。同时通过正交化约束，避免影响 clean utility。

**数学定义：**

设 $P_s$ 为 suspect subspace 的投影矩阵，$P_c$ 为 clean subspace 的投影矩阵。

1. **Suspect-projected perturbation：**
   $$\epsilon^* = \arg\max_{\|\epsilon\| \leq \rho} \mathcal{L}_{\text{trigger}}(\theta + P_s \epsilon)$$
   
   使用一步 gradient ascent 近似：
   $$\epsilon^* \approx \rho \cdot \frac{P_s \nabla_\theta \mathcal{L}_{\text{trigger}}(\theta)}{\|P_s \nabla_\theta \mathcal{L}_{\text{trigger}}(\theta)\|}$$

2. **正交化：** 确保扰动方向与 clean gradient 正交：
   $$\hat{\epsilon} = \epsilon^* - \frac{\epsilon^{*\top} g_{\text{clean}}}{\|g_{\text{clean}}\|^2} g_{\text{clean}}$$

3. **Sharpness ascent update：**
   $$\theta \leftarrow \theta + \alpha_{\text{SA}} \cdot \hat{\epsilon}$$
   
   注意这里是 **加** 而不是减——目标是增大 suspect 方向的 sharpness，而不是最小化 loss。

**与 SAM/ASAM 的区别：**
- SAM 在**全参数空间**做 sharpness minimization（找平坦最小值）
- FT-SAM 用 SAM 做后门防御（全局 sharpness-aware fine-tuning）
- BasinBreaker 的 OSA 在**suspect subspace 内**做 sharpness **maximization**（打碎后门盆地），同时在 clean subspace 内保持稳定

**步长选择：** $\alpha_{\text{SA}} = \alpha_0 \cdot \min(1, \frac{\delta_{\text{CA}}}{\|\hat{\epsilon}\|})$，其中 $\delta_{\text{CA}}$ 是允许的 clean accuracy 下降阈值。

**Layer-wise normalization：** 对每一层单独归一化扰动幅度，防止某些层被过度扰动：
$$\hat{\epsilon}^{(l)} = \hat{\epsilon}^{(l)} \cdot \frac{\|\theta^{(l)}\|}{\|\hat{\epsilon}^{(l)}\| + \epsilon}$$

### 5.3 Subspace Reset / Reprojection

#### 有 Clean Reference Model 时

设 $\theta_{\text{ref}}$ 为 clean reference model 参数。

1. **计算参数差异在 suspect subspace 上的投影：**
   $$\Delta_s = P_s (\theta_0 - \theta_{\text{ref}})$$

2. **部分 reset：**
   $$\theta^* = \theta_0 - \alpha_{\text{reset}} \cdot \Delta_s$$
   
   $\alpha_{\text{reset}} \in [0, 1]$ 控制 reset 强度。$\alpha_{\text{reset}} = 1$ 表示完全 reset suspect 方向到 clean reference。

3. **Trust region 约束：**
   $$\|\theta^* - \theta_0\| \leq r_{\text{trust}}$$
   防止 reset 过度导致模型崩溃。

#### 无 Clean Reference Model 时（默认方案）

1. **EMA Clean Trajectory：** 在 clean fine-tuning 过程中维护 EMA：
   $$\theta_{\text{ema}} = \beta \theta_{\text{ema}} + (1-\beta) \theta_t$$
   用 $\theta_{\text{ema}}$ 作为 pseudo-reference。

2. **Early Checkpoint：** 使用防御过程中 clean loss 最低的 checkpoint 作为 reference。

3. **Layer-wise Mean Statistics：** 对每一层，用 clean data 的 activation statistics（均值、方差）作为 reference anchor，将 suspect 层的 statistics 向 clean 方向拉回。

4. **Self-reference via Noise Injection：** 对 suspect subspace 注入 Gaussian noise $\mathcal{N}(0, \sigma^2 I)$，相当于"模糊化"后门信息，然后用 clean data recovery。

**推荐默认方案：** EMA Clean Trajectory + Early Checkpoint 组合。

#### Adapter / LoRA Setting

- 优先 reset low-rank matrices 的 suspect 方向
- 如果 rank collapse 严重，重新初始化 suspect adapter 并用 clean data 重训
- 只 reset projection head 和 adapter weights，冻结 backbone

### 5.4 Stability-constrained Recovery

防御的最后阶段：用 clean data 恢复 utility，同时约束模型不回到 suspect basin。

**总体优化目标：**
$$\min_\theta \; \mathcal{L}_{\text{recovery}} = \underbrace{\mathcal{L}_{\text{CLIP}}(\theta; \mathcal{D}_c)}_{\text{clean contrastive loss}} + \mu_1 \underbrace{\|f_\theta(x) - f_{\theta_{\text{ref}}}(x)\|^2}_{\text{feature consistency}} + \mu_2 \underbrace{\|P_s(\theta - \theta^*_{\text{post-SA}})\|^2}_{\text{suspect avoidance}} + \mu_3 \underbrace{\|\theta - \theta^*_{\text{post-SA}}\|^2}_{\text{parameter trust region}}$$

各项说明：
- **Clean contrastive loss：** 标准 CLIP 对比学习损失，恢复图文对齐能力
- **Feature consistency：** 保持与 reference（或 EMA）的特征一致性，防止表示漂移
- **Suspect avoidance：** 惩罚模型在 suspect subspace 方向上回到 pre-defense 位置
- **Parameter trust region：** 限制参数偏离 post-sharpness-ascent 位置的幅度

**Layer-wise freeze 策略：**
- 对 suspect score 最低的层完全冻结（不参与 recovery）
- 对 suspect score 最高的层使用更小的 learning rate
- Projection head 始终参与 recovery（因为它直接影响对齐质量）

### 5.5 Anti-rebound Objective

这是 BasinBreaker 区别于所有现有防御的核心模块。目标是：**不仅让当前 ASR 低，还让模型在未来 clean fine-tuning 后 ASR 不反弹。**

#### 精确 Unrolled 版本

**思路：** 显式模拟 $K$ 步 clean fine-tuning，将最终 ASR 写入防御目标。

设当前防御参数为 $\theta$，模拟 $K$ 步 clean SGD：
$$\theta_0' = \theta, \quad \theta_{k+1}' = \theta_k' - \eta_{\text{sim}} \nabla_{\theta_k'} \mathcal{L}_{\text{clean}}(\theta_k'; \mathcal{D}_c)$$

Anti-rebound loss：
$$\mathcal{L}_{\text{AR}}^{\text{exact}} = \frac{1}{K} \sum_{k=1}^{K} \text{ASR}(\theta_k')$$

由于 ASR 不可微，用 trigger proxy loss 替代：
$$\mathcal{L}_{\text{AR}}^{\text{exact}} = \frac{1}{K} \sum_{k=1}^{K} \mathcal{L}_{\text{trigger}}(\theta_k'; \tilde{\mathcal{D}})$$

其中 $\tilde{\mathcal{D}}$ 是用 trigger proxy 构造的 triggered batch。

**反向传播：** 需要 through $K$ 步优化过程反传梯度（类似 MAML）。

**计算成本：** 每个 defense step 需要 $K$ 次额外 forward-backward pass，显存需要存储 $K$ 步的计算图。$K=5$ 时约 6× vanilla FT 成本。

**适用场景：** 仅用于理论验证和消融实验，不作为默认方案。

#### 一阶近似版本（推荐默认方案）

**思路：** 用 Taylor 展开近似 $K$ 步后的参数，避免 unrolled 计算图。

单步 clean FT 后的参数近似：
$$\theta_1' \approx \theta - \eta_{\text{sim}} \nabla_\theta \mathcal{L}_{\text{clean}}(\theta)$$

Anti-rebound loss 的一阶近似：
$$\mathcal{L}_{\text{AR}}^{\text{1st}} = \mathcal{L}_{\text{trigger}}(\theta - \eta_{\text{sim}} \nabla_\theta \mathcal{L}_{\text{clean}}(\theta); \tilde{\mathcal{D}})$$

进一步展开：
$$\mathcal{L}_{\text{AR}}^{\text{1st}} \approx \mathcal{L}_{\text{trigger}}(\theta) - \eta_{\text{sim}} \nabla_\theta \mathcal{L}_{\text{trigger}}(\theta)^\top \nabla_\theta \mathcal{L}_{\text{clean}}(\theta)$$

第二项正是 **clean gradient 与 trigger gradient 的内积**——这与 BadCLIP++ 的 Theorem 1（gradient co-directionality）直接对应。最小化这个 loss 等价于：
- 降低当前 trigger loss（第一项）
- **同时惩罚 clean gradient 与 trigger gradient 的同向性**（第二项）

这意味着 BasinBreaker 的 anti-rebound 机制在理论上直接对抗了 BadCLIP++ 的持久性机制。

**计算成本：** 仅需额外 1 次 forward-backward pass（计算 $\nabla_\theta \mathcal{L}_{\text{clean}}$ 和 $\nabla_\theta \mathcal{L}_{\text{trigger}}$），约 2× vanilla FT 成本。

**多步扩展：** 可以用 $K$ 个不同的 $\eta_{\text{sim}}$ 值做 ensemble：
$$\mathcal{L}_{\text{AR}}^{\text{multi}} = \frac{1}{|\mathcal{H}|} \sum_{\eta \in \mathcal{H}} \mathcal{L}_{\text{trigger}}(\theta - \eta \nabla_\theta \mathcal{L}_{\text{clean}}(\theta))$$
其中 $\mathcal{H} = \{1\text{e-6}, 5\text{e-6}, 1\text{e-5}, 5\text{e-5}\}$，覆盖不同 fine-tuning 强度。

#### 工程可行版本

**思路：** 周期性模拟 fine-tuning，用 cached gradient 降低成本。

1. **Periodic simulation：** 每 $T$ 个 defense step，执行一次 $K$-step simulated clean FT（不反传，只 forward）
2. **Cached gradient：** 缓存最近一次 $\nabla_\theta \mathcal{L}_{\text{clean}}$，在后续 $T$ 步中复用
3. **LoRA-only simulation：** 只在 LoRA 参数上模拟 fine-tuning，大幅降低成本
4. **Stop-gradient trick：** 对 simulated FT 的中间步骤 stop gradient，只对最终 ASR 反传

**计算成本：** 约 1.3-1.5× vanilla FT 成本。

#### 无 Trigger Proxy 时的 Worst-case Rebound Objective

如果没有可靠的 trigger proxy，可以构造 worst-case 目标：

$$\mathcal{L}_{\text{AR}}^{\text{worst}} = \max_{\|\delta\| \leq \epsilon_{\text{trig}}} \mathcal{L}_{\text{align}}(\theta_1'; x + \delta, t_{\text{any}})$$

即：在一步 clean FT 后，寻找最坏情况的 trigger perturbation，使得模型仍然能被某种 trigger 激活。这等价于一个 minimax 问题，可以用交替优化近似。

**推荐：** 优先使用 trigger proxy（InverTune 风格），worst-case 版本作为 ablation。

### 5.6 BasinBreaker 总体算法

**总体优化目标：**
$$\mathcal{L}_{\text{total}} = \underbrace{\mathcal{L}_{\text{CLIP}}(\theta)}_{\text{clean utility}} + \lambda_1 \underbrace{\mathcal{L}_{\text{suppress}}(\theta)}_{\text{trigger suppression}} + \lambda_2 \underbrace{\mathcal{L}_{\text{AR}}^{\text{1st}}(\theta)}_{\text{anti-rebound}} + \lambda_3 \underbrace{\|P_s(\theta - \theta_{\text{anchor}})\|^2}_{\text{suspect avoidance}} + \lambda_4 \underbrace{\|\theta - \theta_{\text{anchor}}\|^2}_{\text{trust region}}$$

其中 $\theta_{\text{anchor}}$ 是 sharpness ascent 后的参数（即 basin-breaking 后的起点）。

**三阶段流程：**

```
Stage 1: Suspect Subspace Identification (1-2 epochs)
  → 输入：poisoned model θ₀, clean data D_c, trigger proxy δ
  → 输出：suspect subspace basis V_s, suspect layers L_s

Stage 2: Basin-Breaking (2-5 epochs)
  → Orthogonal Sharpness Ascent on suspect subspace
  → Subspace Reset / Reprojection
  → 输出：θ_anchor (basin-broken model)

Stage 3: Stability-constrained Recovery + Anti-rebound (5-10 epochs)
  → 优化 L_total
  → 输出：θ* (final defended model)
```

**默认超参数（CLIP ViT-B/32）：**

| 超参数 | 默认值 | 说明 |
|--------|--------|------|
| Suspect subspace rank $r$ | 50 | gradient-difference SVD 的 top-r |
| Suspect layers $L$ | top-6 layers | 按 layer suspect score 排序 |
| SA perturbation radius $\rho$ | 0.05 | sharpness ascent 扰动半径 |
| SA step size $\alpha_{\text{SA}}$ | 0.01 | sharpness ascent 步长 |
| Reset strength $\alpha_{\text{reset}}$ | 0.7 | suspect subspace reset 强度 |
| Recovery learning rate | 1e-6 | stability-constrained recovery |
| Anti-rebound $\eta_{\text{sim}}$ | 1e-5 | 模拟 fine-tuning 学习率 |
| $\lambda_1$ (suppress) | 1.0 | trigger suppression 权重 |
| $\lambda_2$ (anti-rebound) | 0.5 | anti-rebound 权重 |
| $\lambda_3$ (suspect avoidance) | 0.1 | suspect avoidance 权重 |
| $\lambda_4$ (trust region) | 0.01 | trust region 权重 |
| Clean data budget | 5K pairs | clean 图文对数量 |
| Defense total epochs | 10-15 | 三阶段总 epoch 数 |
| Batch size | 256 | 标准 CLIP batch size |

---

## 6. 主实验设计

### 6.1 模型选择

**主实验（Main Paper）：**

| 模型 | 参数量 | 角色 |
|------|--------|------|
| CLIP ViT-B/32 | ~150M | 主要实验模型，所有方法在此对比 |
| CLIP RN50 | ~100M | 架构泛化验证（CNN vs Transformer） |
| OpenCLIP ViT-B/32 | ~150M | 训练数据泛化验证（不同预训练数据） |

**Appendix 扩展：**

| 模型 | 角色 |
|------|------|
| CLIP ViT-B/16 | 更高分辨率 patch 的影响 |
| CLIP RN101 | 更深 CNN 的影响 |
| OpenCLIP ViT-B/16 | 交叉验证 |
| ALBEF / BLIP（可选） | 非 CLIP 架构泛化 |

**暂不纳入 LLaVA / MiniGPT-4 等大型 VLM：** 原因是 (1) BadCLIP/BadCLIP++ 主要针对 CLIP 架构；(2) 大型 VLM 的后门机制可能不同；(3) 计算成本过高。但在 Discussion 中应讨论扩展可能性。

### 6.2 数据集选择

| 数据集 | 任务类型 | 角色 | 具体用法 |
|--------|---------|------|---------|
| ImageNet-1K | Zero-shot classification | 主要评估集 | ASR / CA 的主要报告数据集 |
| ImageNet-100 | Zero-shot classification | 快速验证 | 前期实验和消融实验 |
| CIFAR-10 / CIFAR-100 | Linear probe classification | 迁移评估 | 验证后门是否嵌入特征空间 |
| MSCOCO | Image-text retrieval | 跨任务评估 | R@1/5/10，验证对齐质量 |
| Flickr30K | Image-text retrieval | 跨域评估 | 与 MSCOCO 交叉验证 |
| CC3M subset (500K) | 预训练投毒 | 攻击训练集 | BadCLIP/BadCLIP++ 投毒数据源 |
| SBU Captions | Cross-domain FT | Rebound 评估 | 跨域 clean fine-tuning 的数据源 |
| ImageNet-Sketch/V2/A/R | Distribution shift | 鲁棒性评估 | 分布偏移下的 ASR 和 CA |

### 6.3 攻击设置

| 攻击 | Poison Rate | Trigger | Target | 训练细节 |
|------|:-----------:|---------|--------|---------|
| BadCLIP | 0.3% (1500/500K) | 16×16 optimized patch | "banana" | 在 CC3M 500K 上投毒训练，dual-embedding guided |
| BadCLIP++ | 0.3% (1500/500K) | QR-style micro trigger | "banana" | T2T + MPE + ALIGN + EWC，greedy subset selection |
| BadNet-CLIP | 0.5% | 固定 3×3 白色 patch | "banana" | 标准 patch trigger 适配到 CLIP |
| Blended-CLIP | 0.5% | Hello Kitty blended (α=0.1) | "banana" | 标准 blended trigger 适配到 CLIP |

**评估方式：**
- Zero-shot ASR：在 ImageNet-1K 上，带 trigger 的图像被分类为 target class 的比例
- Zero-shot CA：不带 trigger 的图像的 top-1 准确率
- Retrieval ASR：在 MSCOCO 上，带 trigger 的图像检索到 target text 的 R@1
- Linear Probe ASR：冻结特征后，线性分类器在 triggered images 上的 ASR

### 6.4 防御设置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| Clean data budget | 5K 图文对 | 从 CC3M 中随机采样（不含毒样本） |
| Defense epochs | 10-15 | 三阶段总计 |
| Batch size | 256 | |
| Learning rate | 1e-6 (recovery) | Stage 3 |
| 参数更新范围 | 全参数 | 默认更新全部参数 |
| Trigger 知识 | 未知 | 使用 trigger proxy |
| Clean reference model | 默认无 | 有 reference 作为增强实验 |
| GPU | 1× A100 80GB | |

### 6.5 持久性评估协议（Persistence Evaluation Protocol）

**这是本文最重要的实验设计创新。**

防御完成后，对 $\theta^*$ 施加以下后续适配，每种适配记录 ASR 曲线：

**核心评估矩阵：**

| 后续适配 | 参数 | 记录点 |
|---------|------|--------|
| Standard Clean FT | lr=1e-5, ImageNet clean subset | epoch 1, 5, 10, 20, 50 |
| Aggressive Clean FT | lr=1e-4, ImageNet clean subset | epoch 1, 5, 10, 20 |
| Conservative Clean FT | lr=1e-6, ImageNet clean subset | epoch 5, 10, 20, 50 |
| Cross-domain FT | lr=1e-5, SBU Captions | epoch 1, 5, 10, 20 |
| LoRA FT | rank=8, lr=1e-4 | epoch 1, 5, 10, 20 |
| Partial-layer FT | 最后 4 层, lr=1e-5 | epoch 1, 5, 10, 20 |

**核心指标定义：**

1. **Rebound ASR：** $\text{ASR}_{\text{rebound}}(K) = \max_{k \in [1,K]} \text{ASR}(\theta_k^*)$
2. **AURC (Area Under Rebound Curve)：** $\text{AURC}(K) = \frac{1}{K}\sum_{k=1}^K \text{ASR}(\theta_k^*)$
3. **Long-horizon Persistence Score：** $\text{LHPS} = \text{ASR}(\theta_{50}^*) - \text{ASR}(\theta^*)$（50 epoch 后的 ASR 增量）
4. **Utility-Stability Pareto Front：** 以 CA drop 为 x 轴、Rebound ASR 为 y 轴的 Pareto 曲线
5. **Defense Cost：** 防御总 GPU 时间 / vanilla FT 的 GPU 时间

---

## 7. 评价指标体系

### 7.1 核心指标（Main Paper 必须报告）

| 指标 | 定义 | 目标值 | 说明 |
|------|------|--------|------|
| ASR↓ | 当前时刻攻击成功率 | ≤ 5% | 防御后立即测量 |
| CA↑ | Clean accuracy (zero-shot) | ≥ baseline - 2% | 不能为了防御牺牲太多 utility |
| Rebound ASR↓ | $\max_{k \in [1,50]} \text{ASR}(\theta_k^*)$ | ≤ 10% | 50 epoch clean FT 后的最大 ASR |
| AURC↓ | $\frac{1}{K}\sum_{k=1}^K \text{ASR}(\theta_k^*)$ | ≤ 8% | Rebound 曲线下面积 |
| LHPS↓ | $\text{ASR}(\theta_{50}^*) - \text{ASR}(\theta^*)$ | ≤ 5% | 长期持久性分数 |
| CA@50↑ | 50 epoch clean FT 后的 CA | ≥ baseline - 1% | 长期 utility 保持 |
| Defense Cost | GPU hours / vanilla FT hours | ≤ 3× | 计算效率 |

### 7.2 辅助指标（消融和分析用）

| 指标 | 定义 | 用途 |
|------|------|------|
| Persistence Gap | Rebound ASR - ASR_now | 衡量防御的"深度" |
| Curvature Change | $\lambda_{\max}^{\text{after}} / \lambda_{\max}^{\text{before}}$ (suspect subspace) | 验证 basin-breaking 效果 |
| Basin Stability Score | 在 $\|\epsilon\| \leq r$ 内 ASR > 50% 的体积比 | 衡量后门盆地是否被打碎 |
| Gradient Alignment | $\cos(g_{\text{trigger}}, g_{\text{clean}})$ after defense | 验证 anti-rebound 是否打破了梯度同向性 |
| Subspace Overlap | suspect subspace 与 clean subspace 的 principal angle | 验证子空间识别质量 |
| Trigger Proxy Fidelity | proxy trigger 与 ground-truth trigger 的 ASR 差异 | 验证 proxy 质量 |
| Layer-wise ASR Contribution | 逐层冻结后的 ASR 变化 | 分析后门分布 |

### 7.3 Rebound 评估协议（本文核心评估创新）

**标准 Rebound 评估流程：**

```
1. 防御完成 → 记录 ASR_now, CA_now
2. 使用 clean data (5K pairs) 进行 fine-tuning:
   - lr = 1e-5, batch_size = 256, optimizer = AdamW
   - 每 epoch 记录 ASR 和 CA
   - 持续 50 epochs
3. 绘制 Rebound Curve: ASR vs epoch
4. 计算 Rebound ASR, AURC, LHPS
5. 重复 3 次取平均（不同 random seed）
```

**多条件 Rebound 评估（Appendix）：**

| 条件 | 变量 | 目的 |
|------|------|------|
| Learning rate sweep | lr ∈ {1e-6, 5e-6, 1e-5, 5e-5, 1e-4} | 对 lr 的鲁棒性 |
| Data amount | 1K / 5K / 10K / 50K pairs | 对 clean data 量的敏感性 |
| Cross-domain | SBU / CC3M subset / Flickr30K | 跨域 rebound |
| LoRA FT | rank = 4/8/16 | 参数高效微调下的 rebound |
| Longer horizon | 100 / 200 epochs | 极长期稳定性 |

### 7.4 统计显著性要求

- 所有主实验结果报告 **3 次独立运行的均值 ± 标准差**
- Rebound 实验报告 **3 次不同 seed 的 Rebound Curve 包络**
- 关键对比使用 **paired t-test**，p < 0.05 视为显著
- 如果标准差过大（> 5%），增加到 5 次运行

---

## 8. 消融实验设计

### 8.1 模块级消融（最重要）

**目的：** 证明每个模块不可或缺。

| 消融配置 | 移除的模块 | 预期影响 |
|---------|-----------|---------|
| Full BasinBreaker | 无 | 最佳 |
| w/o Subspace Identification | 用全参数空间替代 suspect subspace | ASR 可能更低但 CA 显著下降 |
| w/o Orthogonal SA | 跳过 sharpness ascent | Rebound ASR 显著上升 |
| w/o Subspace Reset | 跳过 reset/reprojection | 当前 ASR 可能更高 |
| w/o Anti-rebound | 移除 $\mathcal{L}_{\text{AR}}$ | Rebound ASR 显著上升 |
| w/o Orthogonalization | SA 不做正交化 | CA 下降明显 |
| w/o Trust Region | 移除 $\lambda_4$ 约束 | 模型可能崩溃 |
| Only FT + Anti-rebound | 无 subspace 识别和 SA | 验证 anti-rebound 单独的价值 |
| Only SA + Recovery | 无 anti-rebound | 验证 basin-breaking 单独的价值 |

**关键对比：**
- Full vs w/o Anti-rebound：证明 anti-rebound 的必要性
- Full vs w/o Orthogonal SA：证明 basin-breaking 的必要性
- Full vs w/o Subspace Identification：证明定向操作优于全局操作

### 8.2 子空间识别方案对比

| 方案 | ASR↓ | CA↑ | Rebound ASR↓ | Cost |
|------|------|-----|-------------|------|
| 方案 A: Hessian eigenspace | 预期最准 | 预期最好 | 预期最低 | 最高 |
| 方案 B: Gradient-difference SVD | 预期接近 A | 预期接近 A | 预期接近 A | 中等 |
| 方案 C: Layer-wise sensitivity | 预期略差 | 预期略差 | 预期略差 | 最低 |
| Random subspace (control) | 预期差 | 预期差 | 预期差 | 最低 |
| Full parameter space (no subspace) | 预期 ASR 低但 CA 崩 | 预期崩 | 不确定 | 中等 |

### 8.3 Anti-rebound 方案对比

| 方案 | Rebound ASR↓ | 计算成本 | 稳定性 |
|------|-------------|---------|--------|
| 一阶近似（默认） | 预期好 | 2× | 高 |
| K=3 Unrolled | 预期最好 | 4× | 中 |
| K=5 Unrolled | 预期最好 | 6× | 中 |
| Multi-η ensemble | 预期好 | 2.5× | 高 |
| Worst-case (no proxy) | 预期中等 | 3× | 低 |
| No anti-rebound | 预期差 | 1× | — |

### 8.4 超参数敏感性分析

**关键超参数扫描：**

| 超参数 | 扫描范围 | 预期趋势 |
|--------|---------|---------|
| Suspect rank $r$ | {10, 20, 50, 100, 200} | 过小→miss backdoor，过大→影响 clean |
| SA radius $\rho$ | {0.01, 0.03, 0.05, 0.1, 0.2} | 过小→无效，过大→CA 崩 |
| Reset strength $\alpha_{\text{reset}}$ | {0.3, 0.5, 0.7, 0.9, 1.0} | 过小→后门残留，过大→CA 下降 |
| Anti-rebound weight $\lambda_2$ | {0.1, 0.3, 0.5, 1.0, 2.0} | 过小→rebound，过大→过拟合 anti-rebound |
| Clean data budget | {1K, 2K, 5K, 10K, 20K} | 越多越好，但边际递减 |
| Defense epochs | {5, 10, 15, 20, 30} | 过少→不充分，过多→过拟合 |

**展示方式：** 每个超参数画一张 ASR / CA / Rebound ASR 三线图，标注推荐区间。

### 8.5 攻击强度敏感性

| 攻击参数 | 扫描范围 | 目的 |
|---------|---------|------|
| Poison rate | {0.1%, 0.3%, 0.5%, 1.0%, 3.0%} | 不同投毒率下的防御效果 |
| Trigger size | {8×8, 16×16, 32×32} | 不同触发器大小的影响 |
| Target class | {banana, airplane, dog, car, ...} | 不同目标类的影响 |
| Persistence strength | BadCLIP++ w/ and w/o EWC | EWC 对防御难度的影响 |

### 8.6 消融实验展示建议

- **模块级消融：** 表格 + 柱状图
- **方案对比：** 表格 + Rebound Curve 对比图
- **超参数敏感性：** 折线图（x 轴为超参数值，y 轴为指标）
- **攻击强度：** 热力图（x 轴为攻击参数，y 轴为防御方法，颜色为 Rebound ASR）

---

## 9. 理论分析方向

### 9.1 理论分析的定位

本文的理论分析不追求完全严格的深度网络全局证明（这在当前技术条件下不现实），而是提供一个**局部二阶近似框架**，解释以下三个核心问题：

1. 为什么持久性后门能在 clean fine-tuning 后存活？
2. 为什么 BasinBreaker 的 sharpness ascent 能降低后门稳定性？
3. 为什么 anti-rebound 训练能防止后门复活？

### 9.2 关键假设

**假设 1（局部光滑性）：** 在 $\theta_0$ 的邻域 $\mathcal{B}(\theta_0, R)$ 内，$\mathcal{L}_{\text{clean}}$ 和 $\mathcal{L}_{\text{trigger}}$ 均为 $L$-Lipschitz 光滑的，即 Hessian 特征值有界：$\|H\| \leq L$。

**假设 2（子空间可分性）：** 存在正交分解 $\mathbb{R}^n = \mathcal{S}_{\text{clean}} \oplus \mathcal{S}_{\text{suspect}} \oplus \mathcal{S}_{\text{rest}}$，使得 clean loss 主要沿 $\mathcal{S}_{\text{clean}}$ 变化，trigger loss 主要沿 $\mathcal{S}_{\text{suspect}}$ 变化。

**假设 3（低曲率盆地）：** 在 $\mathcal{S}_{\text{suspect}}$ 方向上，$\theta_0$ 处的 Hessian 特征值满足 $\lambda_i^{\text{suspect}} \leq \lambda_{\text{low}}$（低曲率），而在 $\mathcal{S}_{\text{clean}}$ 方向上 $\lambda_j^{\text{clean}} \geq \lambda_{\text{high}}$（正常曲率），且 $\lambda_{\text{low}} \ll \lambda_{\text{high}}$。

### 9.3 定理候选

**Proposition 1（Clean FT 无法逃离低曲率盆地）：**

在假设 1-3 下，若 clean fine-tuning 使用学习率 $\eta \leq 1/L$，则经过 $K$ 步 clean SGD 后，参数在 suspect subspace 上的位移满足：
$$\|P_s(\theta_K - \theta_0)\| \leq K \eta \cdot \lambda_{\text{low}} \cdot \|P_s \theta_0\| + O(\eta^2 K^2)$$

当 $\lambda_{\text{low}}$ 足够小时，$K$ 步 clean FT 几乎不改变 suspect subspace 中的参数——后门因此"存活"。

**证明思路：** 在 suspect subspace 上做 Taylor 展开，clean loss 的梯度在该方向上的分量由 $H_{\text{clean}}$ 在 suspect 方向上的投影决定。由于假设 2（子空间可分性），$P_s \nabla \mathcal{L}_{\text{clean}} \approx P_s H_{\text{clean}} P_s (\theta - \theta^*)$，其特征值受 $\lambda_{\text{low}}$ 约束。

**Proposition 2（Sharpness Ascent 提升 Rebound 代价）：**

设 BasinBreaker 的 orthogonal sharpness ascent 将 suspect subspace 上的最小 Hessian 特征值从 $\lambda_{\text{low}}$ 提升到 $\lambda_{\text{high}}'$。则防御后模型 $\theta^*$ 在 $K$ 步 clean FT 后的 trigger loss 变化满足：
$$|\mathcal{L}_{\text{trigger}}(\theta_K^*) - \mathcal{L}_{\text{trigger}}(\theta^*)| \leq C \cdot \frac{\lambda_{\text{high}}'}{\lambda_{\text{high}}' + \lambda_{\text{clean}}} \cdot K\eta$$

当 $\lambda_{\text{high}}'$ 增大时，trigger loss 的变化幅度受到更强约束——后门更难通过 clean FT "滑回"低 loss 区域。

**证明思路：** 利用 sharpness ascent 后的 Hessian 变化，分析 clean FT 轨迹在 suspect subspace 上的投影。高曲率意味着 clean FT 的梯度在 suspect 方向上有更强的"回复力"，阻止参数回到后门盆地。

**Proposition 3（Anti-rebound 打破梯度同向性）：**

BadCLIP++ 的 Theorem 1 证明了在其优化后，$\cos(g_{\text{trigger}}, g_{\text{clean}}) > 0$（梯度同向）。BasinBreaker 的 anti-rebound loss $\mathcal{L}_{\text{AR}}^{\text{1st}}$ 的梯度包含项：
$$\nabla_\theta \mathcal{L}_{\text{AR}}^{\text{1st}} \ni -\eta_{\text{sim}} \nabla_\theta [g_{\text{trigger}}^\top g_{\text{clean}}]$$

这直接惩罚 trigger gradient 与 clean gradient 的内积，从而打破 BadCLIP++ 精心构造的梯度同向性。

**证明思路：** 直接对 $\mathcal{L}_{\text{AR}}^{\text{1st}}$ 求梯度，展开后可以看到包含 $-\eta_{\text{sim}} H_{\text{trigger}} g_{\text{clean}} - \eta_{\text{sim}} H_{\text{clean}} g_{\text{trigger}}$ 项，这些项的方向与 $g_{\text{trigger}}^\top g_{\text{clean}} > 0$ 的条件对抗。

**Theorem 1（Rebound Upper Bound）：**

综合 Proposition 1-3，在 BasinBreaker 防御后，$K$ 步 clean FT 的 rebound ASR 满足：
$$\text{ASR}(\theta_K^*) \leq \text{ASR}(\theta^*) + C_1 \cdot \exp(-C_2 \cdot \lambda_{\text{high}}' \cdot K\eta) + C_3 \cdot |\cos(g_{\text{trigger}}, g_{\text{clean}})|_{\theta^*}$$

其中 $C_1, C_2, C_3$ 为常数。当 $\lambda_{\text{high}}'$ 大（basin 被打碎）且 $|\cos(g_{\text{trigger}}, g_{\text{clean}})|$ 小（梯度同向性被打破）时，rebound 被有效抑制。

### 9.4 可视化验证方式

- **Proposition 1 验证：** 对比 clean FT 前后参数在 suspect subspace 上的位移量（BadCLIP++ vs clean model）
- **Proposition 2 验证：** 对比 SA 前后 suspect subspace 的 Hessian 特征值变化
- **Proposition 3 验证：** 对比防御前后 $\cos(g_{\text{trigger}}, g_{\text{clean}})$ 的分布
- **Theorem 1 验证：** 绘制理论 bound 与实际 rebound ASR 的对比曲线

### 9.5 审稿人可能质疑点

| 质疑 | 应对 |
|------|------|
| "假设 2 太强，子空间不一定正交" | 放松为近似正交（principal angle > 60°），实验验证 |
| "局部分析不能推广到全局" | 明确声明是局部解释框架，不是全局保证；用实验补充 |
| "Hessian 特征值在训练中会变" | 分析 defense 过程中特征值的动态变化，证明趋势一致 |
| "理论 bound 太松" | 承认 bound 是 order-of-magnitude 级别，重点在定性解释 |

---

## 10. 可视化与可解释性实验

### 10.1 Loss Landscape / ASR Landscape（Figure 2 候选）

**生成方式：** 使用 Li et al. (2018) 的 loss landscape visualization 方法。选择两个方向：(1) suspect subspace 的第一主方向 $v_1$；(2) clean subspace 的第一主方向 $u_1$。在 $(\alpha, \beta)$ 网格上计算 $\text{ASR}(\theta + \alpha v_1 + \beta u_1)$。

**横轴：** suspect direction 位移 $\alpha$  
**纵轴：** clean direction 位移 $\beta$  
**颜色：** ASR 值（热力图）

**预期现象：**
- 防御前：沿 suspect direction 存在宽而平的高 ASR 盆地
- 防御后（BasinBreaker）：盆地变窄、变陡，ASR 快速下降
- 防御后（CleanCLIP）：盆地仍然存在，只是中心 ASR 略低

**论文作用：** 这是最直观的 motivation figure，直接展示"为什么现有防御不够"和"BasinBreaker 做了什么"。

### 10.2 Hessian 特征谱对比（Figure 3 候选）

**生成方式：** 对 clean / BadCLIP / BadCLIP++ / BasinBreaker-defended 四个模型，计算 Hessian top-50 特征值。

**横轴：** 特征值序号（1-50）  
**纵轴：** 特征值大小（log scale）  
**四条线：** 四个模型

**预期现象：**
- BadCLIP++ 的特征值整体偏小（尤其在 suspect 方向）
- BasinBreaker 防御后，suspect 方向的特征值显著增大
- Clean model 的特征值分布作为 reference

### 10.3 Rebound Curve 对比（Figure 4 候选，最重要的结果图）

**生成方式：** 防御后 50 epoch clean FT，每 epoch 记录 ASR。

**横轴：** Clean FT epoch (0-50)  
**纵轴：** ASR (%)  
**多条线：** 不同防御方法（CleanCLIP / InverTune / FT-SAM / BasinBreaker / No defense）

**预期现象：**
- No defense：ASR 始终高（~99%）
- CleanCLIP：ASR 先降后升（rebound）
- InverTune：ASR 降到很低，但 10-20 epoch 后开始回升
- FT-SAM：比 CleanCLIP 好，但仍有 rebound
- BasinBreaker：ASR 降到很低且保持稳定

### 10.4 Gradient Alignment 分布（Figure 5 候选）

**生成方式：** 在 defense 前后，采样 1000 个 mini-batch，计算 $\cos(g_{\text{trigger}}, g_{\text{clean}})$，绘制直方图。

**横轴：** $\cos(g_{\text{trigger}}, g_{\text{clean}})$ 值 (-1 到 1)  
**纵轴：** 频率  
**三组：** 防御前 / CleanCLIP 后 / BasinBreaker 后

**预期现象：**
- 防御前（BadCLIP++）：分布偏正（~0.7-0.9），梯度高度同向
- CleanCLIP 后：分布略向 0 移动，但仍偏正
- BasinBreaker 后：分布集中在 0 附近或偏负，梯度同向性被打破

### 10.5 Layer-wise Suspect Score Heatmap（Figure 6 候选）

**生成方式：** 对每一层计算 suspect score（方案 C），绘制热力图。

**横轴：** 层编号  
**纵轴：** 不同攻击方法  
**颜色：** Suspect score

**预期现象：** BadCLIP++ 的 suspect score 集中在中间层和 cross-attention 层。

### 10.6 t-SNE / PCA 表示空间可视化（Figure 7 候选）

**生成方式：** 对 clean / triggered / target-class 图像的 CLIP 视觉嵌入做 t-SNE。

**四个子图：** 防御前 / CleanCLIP 后 / InverTune 后 / BasinBreaker 后

**预期现象：**
- 防御前：triggered 样本聚集在 target class 附近
- CleanCLIP 后：triggered 样本部分散开，但仍有残留聚集
- BasinBreaker 后：triggered 样本完全散开，不再聚集

### 10.7 Defense Trajectory in Parameter Space（Figure 8 候选）

**生成方式：** 将 defense 过程中的参数轨迹投影到 suspect subspace 的前两个主方向上。

**横轴/纵轴：** suspect direction 1 / suspect direction 2  
**轨迹：** defense 过程中参数的移动路径  
**背景：** ASR 等高线

**预期现象：** BasinBreaker 的轨迹先远离后门盆地中心（SA 阶段），然后在低 ASR 区域稳定（recovery 阶段）。

### 10.8 Utility-ASR Pareto Curve（Figure 9 候选）

**生成方式：** 对不同防御方法，以不同超参数强度运行，收集 (CA drop, Rebound ASR) 点对。

**横轴：** CA drop (%)  
**纵轴：** Rebound ASR (%)  
**多条线：** 不同方法的 Pareto front

**预期现象：** BasinBreaker 的 Pareto front 严格优于其他方法（同等 CA drop 下 Rebound ASR 更低）。

---

## 11. 工程实现计划

### 11.1 推荐代码结构

```
basin-breaker/
├── attacks/                    # 攻击复现
│   ├── badclip/               # BadCLIP 攻击代码
│   ├── badclip_pp/            # BadCLIP++ 攻击代码
│   ├── patch_trigger.py       # BadNet-CLIP
│   ├── blended_trigger.py     # Blended-CLIP
│   └── utils.py               # 触发器工具函数
├── defenses/                   # 防御方法
│   ├── basin_breaker/         # 本文方法
│   │   ├── subspace_id.py     # 子空间识别（方案 A/B/C）
│   │   ├── sharpness_ascent.py # 正交锐度上升
│   │   ├── reprojection.py    # 子空间重投影/reset
│   │   ├── recovery.py        # Stability-constrained recovery
│   │   ├── anti_rebound.py    # Anti-rebound objective
│   │   └── pipeline.py        # 三阶段完整流程
│   ├── cleanclip.py           # CleanCLIP baseline
│   ├── invertune.py           # InverTune baseline
│   ├── ft_sam.py              # FT-SAM baseline
│   ├── anp.py                 # ANP baseline
│   └── vanilla_ft.py          # Vanilla fine-tuning
├── models/                     # 模型加载
│   ├── clip_loader.py         # CLIP / OpenCLIP 加载
│   └── trigger_proxy.py       # Trigger proxy 生成
├── data/                       # 数据处理
│   ├── imagenet.py            # ImageNet 数据加载
│   ├── coco.py                # MSCOCO 数据加载
│   ├── cc3m.py                # CC3M 数据加载
│   └── poison_dataset.py      # 投毒数据集构造
├── eval/                       # 评估模块
│   ├── asr.py                 # ASR 计算
│   ├── clean_acc.py           # Clean accuracy
│   ├── retrieval.py           # Retrieval R@K
│   ├── rebound.py             # Rebound 评估协议
│   ├── curvature.py           # Hessian / Fisher 分析
│   └── metrics.py             # AURC, LHPS 等指标
├── analysis/                   # 分析与可视化
│   ├── loss_landscape.py      # Loss landscape 可视化
│   ├── hessian_spectrum.py    # Hessian 特征谱
│   ├── gradient_alignment.py  # 梯度同向性分析
│   ├── tsne_viz.py            # t-SNE 可视化
│   └── rebound_curve.py       # Rebound 曲线绘制
├── configs/                    # 实验配置
│   ├── attack/                # 攻击配置
│   ├── defense/               # 防御配置
│   └── eval/                  # 评估配置
├── scripts/                    # 运行脚本
│   ├── run_attack.sh          # 攻击训练
│   ├── run_defense.sh         # 防御运行
│   ├── run_rebound.sh         # Rebound 评估
│   └── run_ablation.sh        # 消融实验
└── README.md
```

### 11.2 需要复现的攻击代码

| 攻击 | 代码来源 | 复现难度 | 优先级 |
|------|---------|---------|--------|
| BadCLIP | 作者开源（GitHub） | 低 | P0 |
| BadCLIP++ | 可能未开源，需根据论文复现 | 高 | P0 |
| BadNet-CLIP | 自行实现（简单 patch） | 低 | P1 |
| Blended-CLIP | 自行实现（blended trigger） | 低 | P1 |

**BadCLIP++ 复现要点：**
- T2T aggregation loss：让 triggered 样本嵌入聚成紧密簇
- MPE multi-prototype enhancement：簇中心对齐目标类中心
- ALIGN cross-modal alignment：图文后门链路相互支撑
- EWC elastic weight consolidation：限制参数偏离预训练
- Greedy Mean Alignment 子集选择：选择最有利的投毒样本
- QR-style micro trigger：黑白二维码风格触发器

### 11.3 需要实现的 Defense Module

| 模块 | 核心依赖 | 实现难度 | 优先级 |
|------|---------|---------|--------|
| Gradient-difference SVD (方案 B) | torch.linalg.svd / randomized SVD | 中 | P0 |
| Layer-wise sensitivity (方案 C) | 标准 backward pass | 低 | P0 |
| Hessian eigenspace (方案 A) | PyHessian / Hutchinson estimator | 高 | P1 |
| Orthogonal Sharpness Ascent | SAM-style perturbation + projection | 中 | P0 |
| Subspace Reprojection | 线性代数投影 | 低 | P0 |
| Stability-constrained Recovery | 标准 fine-tuning + regularization | 低 | P0 |
| Anti-rebound (一阶近似) | 额外 forward-backward pass | 中 | P0 |
| Anti-rebound (unrolled) | higher-order autograd / MAML-style | 高 | P2 |
| Trigger proxy generation | InverTune 风格 trigger inversion | 高 | P0 |

### 11.4 Hessian-vector Product 实现

```python
# PyTorch 实现 Hessian-vector product（不需要显式构造 Hessian）
def hvp(loss_fn, params, v):
    """计算 Hessian-vector product: H @ v"""
    grads = torch.autograd.grad(loss_fn, params, create_graph=True)
    flat_grad = torch.cat([g.flatten() for g in grads])
    hvp_result = torch.autograd.grad(flat_grad, params, grad_outputs=v)
    return torch.cat([h.flatten() for h in hvp_result])

# Lanczos 迭代提取 top-r 特征向量
def lanczos_top_eigenvectors(loss_fn, params, r=50, n_iter=100):
    """使用 Lanczos 算法提取 Hessian top-r 特征向量"""
    # 初始化随机向量
    q = torch.randn(total_params).to(device)
    q = q / q.norm()
    # Lanczos 迭代...
    # 返回 top-r eigenvectors 和 eigenvalues
```

### 11.5 Unrolled Anti-rebound 实现

```python
# 一阶近似版本（推荐默认）
def anti_rebound_first_order(model, clean_batch, trigger_batch, eta_sim):
    # 计算 clean gradient
    clean_loss = compute_clip_loss(model, clean_batch)
    clean_grads = torch.autograd.grad(clean_loss, model.parameters())
    
    # 模拟一步 clean FT
    with torch.no_grad():
        for p, g in zip(model.parameters(), clean_grads):
            p.data -= eta_sim * g
    
    # 计算模拟后的 trigger loss
    trigger_loss = compute_trigger_loss(model, trigger_batch)
    
    # 恢复参数
    with torch.no_grad():
        for p, g in zip(model.parameters(), clean_grads):
            p.data += eta_sim * g
    
    return trigger_loss  # 最小化这个 loss
```

### 11.6 硬件预算

| 阶段 | GPU 需求 | 预计时间 |
|------|---------|---------|
| 攻击复现（BadCLIP + BadCLIP++） | 1× A100 80GB | 1-2 周 |
| 前期实验 P1-P5 | 1× A100 80GB | 2-3 周 |
| BasinBreaker v1 开发与调试 | 1× A100 80GB | 2-3 周 |
| 主实验（3 模型 × 4 攻击 × 6 防御） | 2× A100 80GB | 3-4 周 |
| 消融实验 | 1× A100 80GB | 2-3 周 |
| Rebound 评估（50 epoch × 多条件） | 1× A100 80GB | 1-2 周 |
| 可视化与分析 | 1× A100 80GB | 1 周 |
| **总计** | **2× A100 80GB** | **约 12-16 周** |

### 11.7 Sanity Check 清单

在正式实验前，必须通过以下检查：

1. ✅ Clean CLIP 在 ImageNet 上的 zero-shot accuracy 与官方报告一致（±1%）
2. ✅ BadCLIP 复现的 ASR 与原论文一致（±3%）
3. ✅ BadCLIP++ 复现的 ASR 和 rebound 行为与原论文一致
4. ✅ CleanCLIP baseline 的防御效果与原论文一致
5. ✅ Trigger proxy 的 ASR 与 ground-truth trigger 的 ASR 差距 < 10%
6. ✅ Hessian-vector product 的数值正确性（与有限差分对比）
7. ✅ Gradient-difference SVD 的子空间与 ground-truth trigger direction 有 > 50% 重叠
8. ✅ Orthogonal SA 后 clean accuracy 下降 < 5%
9. ✅ Anti-rebound loss 的梯度方向与预期一致（惩罚梯度同向性）
10. ✅ 完整 pipeline 在 ImageNet-100 上端到端运行无 bug

---

## 12. 阶段性研究计划

### Phase 0: Literature & Codebase Preparation（第 1-2 周）

**目标：** 完成文献调研、代码框架搭建、环境配置。

**任务：**
- 精读 BadCLIP、BadCLIP++、InverTune、FT-SAM、PAM、CleanCLIP 论文
- 搭建代码框架（上述目录结构）
- 配置实验环境（PyTorch 2.x, CLIP, OpenCLIP, wandb）
- 下载预训练模型和数据集
- 复现 BadCLIP 攻击（使用开源代码）

**产出：** 可运行的攻击代码、数据 pipeline、评估脚本。  
**风险：** BadCLIP++ 可能未开源，需要从论文复现。  
**Go/No-go：** BadCLIP 复现 ASR > 95%。

### Phase 1: Reproduce Persistent Rebound Phenomenon（第 3-4 周）

**目标：** 验证 rebound 现象确实存在，建立 motivation。

**任务：**
- 复现 BadCLIP++ 攻击（如未开源则根据论文实现）
- 实现 CleanCLIP、Vanilla FT、FT-SAM baseline
- 运行实验 P1：防御后 50 epoch clean FT 的 rebound 评估
- 绘制 rebound curve

**产出：** Rebound 现象的经验证据（Figure 1 候选）。  
**成功标准：** 至少一种现有防御在 BadCLIP++ 下出现 > 20% rebound ASR。  
**Go/No-go：** 如果 rebound 不存在，需要重新评估整个方向。

### Phase 2: Validate Geometry Hypothesis（第 5-6 周）

**目标：** 验证持久性后门确实对应低曲率子空间。

**任务：**
- 实现 Hessian 特征谱分析（PyHessian / Hutchinson）
- 实现 gradient-difference SVD 子空间识别
- 运行实验 P2（曲率分析）和 P3（方向可识别性）
- 分析 trigger-sensitive 方向与 clean-sensitive 方向的关系

**产出：** 曲率分析结果、子空间可视化（Figure 2-3 候选）。  
**成功标准：** Suspect subspace 的曲率显著低于 clean subspace（> 50% 差异）。  
**Go/No-go：** 如果曲率假设不成立，需要换用其他几何指标（如 Fisher 信息、gradient covariance）。

### Phase 3: Implement BasinBreaker v1（第 7-9 周）

**目标：** 实现完整 BasinBreaker 算法并在 ImageNet-100 上验证。

**任务：**
- 实现 Orthogonal Sharpness Ascent（实验 P4）
- 实现 Subspace Reset / Reprojection
- 实现 Stability-constrained Recovery
- 实现 Anti-rebound objective（一阶近似版，实验 P5）
- 在 CLIP ViT-B/32 + BadCLIP++ + ImageNet-100 上端到端测试
- 超参数初步调优

**产出：** BasinBreaker v1 代码、ImageNet-100 上的初步结果。  
**成功标准：** Rebound ASR < 15%（50 epoch），CA drop < 3%。  
**Go/No-go：** 如果 Rebound ASR > 30%，需要诊断哪个模块失效并修复。

### Phase 4: Full Main Experiments（第 10-13 周）

**目标：** 完成所有主实验和 rebound 评估。

**任务：**
- 在 3 个模型 × 4 种攻击 × 6 种防御上运行完整实验
- 运行完整 persistence evaluation protocol（6 种后续适配）
- 收集所有主实验数据
- 实现 InverTune baseline（如需要）

**产出：** 主实验表格、rebound curve 图、跨模型/跨攻击结果。  
**成功标准：** BasinBreaker 在 Rebound ASR 上显著优于所有 baseline（> 15% 改善）。

### Phase 5: Ablation, Theory, Visualization（第 14-16 周）

**目标：** 完成消融实验、理论分析验证和可视化。

**任务：**
- 运行全部消融实验（模块级、方案对比、超参数敏感性）
- 验证理论 Proposition 1-3（经验验证）
- 生成所有可视化图表
- 补充 appendix 实验（更多模型、更多攻击、更多条件）

**产出：** 消融表格、理论验证图、完整可视化。  
**成功标准：** 每个模块的消融都显示不可或缺性。

### Phase 6: Paper Writing & Rebuttal Preparation（第 17-20 周）

**目标：** 完成论文撰写和预审。

**任务：**
- 撰写论文初稿（按 Section 15 的故事线）
- 内部审稿 2-3 轮
- 准备 rebuttal 预案（针对 Section 1.5 的质疑点）
- 整理代码和 supplementary material
- 提交

**产出：** 完整论文、supplementary、代码包。

### 阶段间依赖与 Go/No-go 信号

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5 ──→ Phase 6
              │            │            │
         [rebound      [曲率假设    [v1 效果
          存在？]       成立？]      达标？]
              │            │            │
           No→重定义    No→换指标    No→诊断修复
```

---

## 13. 预期结果标准

### 13.1 最低可投稿标准（Tier-2 会议 / Workshop）

| 指标 | 要求 |
|------|------|
| 攻击覆盖 | BadCLIP + BadCLIP++ 两种攻击 |
| 模型覆盖 | CLIP ViT-B/32 一个模型 |
| ASR↓ | ≤ 10% |
| CA drop | ≤ 3% |
| Rebound ASR (20 epoch) | ≤ 20%，且优于最强 baseline ≥ 10% |
| Baseline 数量 | ≥ 3 个（CleanCLIP, FT-SAM, Vanilla FT） |
| 消融 | 模块级消融（4 组） |
| 理论 | 无严格要求，但需要 motivation 分析 |

### 13.2 强顶会标准（NeurIPS / ICML / ICLR）

| 指标 | 要求 |
|------|------|
| 攻击覆盖 | 4 种攻击（BadCLIP, BadCLIP++, BadNet-CLIP, Blended-CLIP） |
| 模型覆盖 | 3 个模型（CLIP ViT-B/32, CLIP RN50, OpenCLIP ViT-B/32） |
| ASR↓ | ≤ 5% |
| CA drop | ≤ 2% |
| Rebound ASR (50 epoch) | ≤ 10%，且优于最强 baseline ≥ 15% |
| AURC | ≤ 8%，且优于最强 baseline ≥ 10% |
| Baseline 数量 | ≥ 5 个（含 InverTune, FT-SAM） |
| 消融 | 完整模块级 + 方案对比 + 超参数敏感性 |
| 理论 | Proposition 1-3 + 经验验证 |
| 可视化 | Loss landscape + Rebound curve + Hessian spectrum + Gradient alignment |
| 跨条件 Rebound | ≥ 3 种后续适配条件（Standard FT, Cross-domain FT, LoRA FT） |

### 13.3 安全四大强竞争力标准（S&P / USENIX Security / CCS / NDSS）

| 指标 | 要求 |
|------|------|
| 攻击覆盖 | ≥ 4 种攻击，含最新持久性攻击 |
| 模型覆盖 | ≥ 3 个模型，含不同架构（CNN + Transformer） |
| 任务覆盖 | Zero-shot classification + Image-text retrieval + Linear probe |
| ASR↓ | ≤ 3% |
| CA drop | ≤ 1.5% |
| Rebound ASR (50 epoch) | ≤ 5%，且优于最强 baseline ≥ 20% |
| AURC | ≤ 5% |
| LHPS | ≤ 3% |
| Baseline 数量 | ≥ 6 个，含最新防御（InverTune, FT-SAM, CleanerCLIP） |
| 消融 | 完整消融 + 攻击强度敏感性 + poison rate 扫描 |
| 理论 | Theorem 1 (Rebound bound) + 完整经验验证 |
| 可视化 | ≥ 8 张高质量图表 |
| 跨条件 Rebound | ≥ 6 种后续适配条件 |
| Trigger 知识 | 必须支持 unknown trigger setting |
| Defense cost | ≤ 3× vanilla FT |
| 新评估协议 | Persistence Evaluation Protocol 作为独立贡献 |
| 安全影响讨论 | 对现有防御有效性声明的挑战 + 负责任披露讨论 |

### 13.4 关键数字目标（量化）

以 BadCLIP++ 攻击、CLIP ViT-B/32 模型、ImageNet-1K 评估为基准：

| 方法 | ASR_now↓ | CA↑ | Rebound ASR (50ep)↓ | AURC↓ |
|------|---------|-----|---------------------|-------|
| No defense | ~99.9% | ~60% | ~99.9% | ~99.9% |
| CleanCLIP | ~3-5% | ~58% | **~40-60%** (rebound) | ~25-35% |
| InverTune | ~0.5% | ~58% | **~20-40%** (预期 rebound) | ~15-25% |
| FT-SAM | ~2-5% | ~58% | **~25-45%** (预期 rebound) | ~18-30% |
| **BasinBreaker** | **≤3%** | **≥58%** | **≤5%** | **≤5%** |

如果 BasinBreaker 能达到上述数字，论文竞争力非常强。

---

## 14. 可能失败模式与备选方案

### 14.1 失败模式 1：后门不对应低曲率子空间

**诊断方式：** Phase 2 实验 P2 中，BadCLIP++ 模型的 suspect subspace 曲率与 clean model 无显著差异。

**可能原因：**
- BadCLIP++ 的持久性不是通过低曲率实现的，而是通过其他机制（如梯度同向性、表示空间聚集）
- Hessian 估计精度不够，噪声掩盖了真实差异

**改进方案：**
- 换用 Fisher 信息矩阵或 gradient covariance 作为替代指标
- 直接用 gradient alignment（$\cos(g_{\text{trigger}}, g_{\text{clean}})$）作为 suspect 判据
- 如果确认曲率假设不成立，将论文重心从"曲率感知"转向"梯度同向性破坏"——这仍然是一个有价值的贡献

**论文转换：** 将 BasinBreaker 重新定位为"Gradient Alignment-aware Defense"，核心贡献变为打破 BadCLIP++ 的梯度同向性。

### 14.2 失败模式 2：Hessian 估计不稳定

**诊断方式：** 不同 random seed 下 Hessian top eigenvectors 差异很大，子空间不可复现。

**改进方案：**
- 增加 Lanczos 迭代次数（100→500）
- 使用 Hutchinson 随机估计的 ensemble（多次估计取平均）
- 放弃精确 Hessian，改用方案 B（gradient-difference SVD）作为默认
- 使用 Fisher 信息矩阵的对角近似（计算稳定且成本低）

**论文转换：** 在消融中展示 Hessian vs Fisher vs gradient-difference 的对比，说明 gradient-difference 是更实用的选择。

### 14.3 失败模式 3：Sharpness Ascent 损害 Clean Utility

**诊断方式：** 任何 $\alpha_{\text{SA}}$ 和 $\rho$ 组合下，CA drop > 5%。

**可能原因：**
- Suspect subspace 与 clean subspace 重叠度高，正交化不够
- SA 步长过大
- 层级选择不够精细

**改进方案：**
- 加强正交化约束（从 soft 改为 hard projection）
- 只在 suspect score 最高的 top-3 层做 SA
- 降低 SA 步长，增加 SA 轮数
- 在 SA 后立即做 utility recovery（交替进行）
- 如果仍然不行，放弃 SA，只保留 subspace reset + anti-rebound

**论文转换：** 如果 SA 不可行，将方法简化为"Subspace Reset + Anti-rebound Training"，仍然是有价值的贡献。

### 14.4 失败模式 4：Anti-rebound 计算成本太高

**诊断方式：** 一阶近似效果不够（rebound ASR > 20%），但 unrolled 版本成本 > 10× vanilla FT。

**改进方案：**
- 使用 multi-η ensemble 一阶近似（覆盖多种 fine-tuning 强度）
- 使用 periodic simulation（每 T 步模拟一次）
- 只在 LoRA 参数上做 unrolled simulation
- 使用 implicit differentiation 近似
- 使用 stop-gradient trick 降低显存

**论文转换：** 在论文中明确报告不同近似方案的 cost-performance tradeoff，将"高效 anti-rebound 近似"作为工程贡献。

### 14.5 失败模式 5：Trigger Proxy 不准确

**诊断方式：** Proxy trigger 的 ASR < 50%，或 proxy 方向与真实 trigger 方向重叠度 < 30%。

**改进方案：**
- 使用多种 proxy 方法的 ensemble
- 使用 adversarial probing（不依赖 trigger inversion）
- 使用 worst-case anti-rebound objective（不依赖 trigger proxy）
- 使用 data-driven 方法：在 clean data 上找 influence score 最高的方向

**论文转换：** 增加"unknown trigger"实验设置，展示 BasinBreaker 在无 trigger proxy 时的 worst-case 性能。

### 14.6 失败模式 6：只对 BadCLIP++ 有效，泛化不足

**诊断方式：** 在 BadNet-CLIP / Blended-CLIP 等简单攻击上效果不如 CleanCLIP。

**可能原因：** 简单攻击的后门不在低曲率子空间中，BasinBreaker 的几何操作"杀鸡用牛刀"。

**改进方案：**
- 增加自适应机制：先检测攻击是否为持久性攻击，再决定是否启用 basin-breaking
- 对简单攻击，只用 recovery + anti-rebound（跳过 SA 和 reset）
- 在论文中明确定位：BasinBreaker 主要针对持久性攻击，对简单攻击至少不劣于现有方法

**论文转换：** 将泛化性作为 discussion 而非 limitation，强调"持久性攻击是更危险的威胁，BasinBreaker 专门解决这个更难的问题"。

### 14.7 失败模式 7：长期 Fine-tuning 后仍然 Rebound

**诊断方式：** 50 epoch 内 rebound ASR < 10%，但 100-200 epoch 后 rebound ASR > 30%。

**改进方案：**
- 增加 anti-rebound 的 horizon（multi-η ensemble 覆盖更大 lr 范围）
- 在 recovery 阶段加入更强的 suspect avoidance 约束
- 使用 periodic re-defense：每 N epoch 重新运行一次轻量 basin-breaking

**论文转换：** 诚实报告长期 rebound 结果，将"防御有效期"作为一个新的评估维度。在 discussion 中讨论"是否存在永久净化"这个开放问题。

### 14.8 失败模式 8：Clean Reference Model 不可用时效果大幅下降

**诊断方式：** 无 reference 版本的 rebound ASR 比有 reference 版本高 > 20%。

**改进方案：**
- 加强 EMA trajectory 的质量（更频繁更新、更大 β）
- 使用 early checkpoint ensemble
- 使用 self-distillation：用 clean data 上的模型输出作为 soft reference

**论文转换：** 在主实验中默认使用无 reference 版本，有 reference 作为增强实验。

---

## 15. 最终论文故事线

### 15.1 Introduction 主线

**第一段：** 多模态对比学习模型（CLIP）已成为视觉-语言 AI 的基础设施，但面临后门攻击威胁。现有防御方法（CleanCLIP、InverTune 等）能在防御后降低 ASR，但...

**第二段（关键转折）：** 我们发现，面对新一代持久性后门攻击（BadCLIP++），现有防御存在一个被忽视的严重问题——**rebound**。防御后的模型在后续 clean fine-tuning 中，ASR 会重新回升到危险水平。这意味着现有防御给了用户一种**虚假的安全感**。

**第三段：** 我们分析发现，rebound 的根源在于持久性后门将参数优化到了一个**低曲率、宽盆地**的稳定子空间中。现有防御只是将参数推到盆地边缘（降低当前 ASR），但没有破坏盆地本身，因此 clean fine-tuning 会将参数重新拉回盆地底部。

**第四段：** 基于这一发现，我们提出 BasinBreaker——首个 persistence-aware 的多模态后门防御。BasinBreaker 通过（1）识别后门子空间，（2）定向提升曲率打碎盆地，（3）子空间重投影，（4）显式 anti-rebound 训练，实现了长期稳定的净化效果。

**第五段：** 我们同时提出了首个系统性的后门持久性评估协议，包括 Rebound ASR、AURC 等指标，为后门防御研究提供了更严格的评估标准。

### 15.2 Motivation Experiment（Section 2 或 3）

**实验 1：** Rebound 现象展示（对应 P1）
- 图：Rebound Curve（不同防御方法在 BadCLIP++ 下的 ASR vs clean FT epoch）
- 结论：所有现有防御都存在显著 rebound

**实验 2：** 曲率分析（对应 P2）
- 图：Hessian 特征谱对比（clean / BadCLIP / BadCLIP++）
- 结论：持久性后门对应低曲率子空间

**实验 3：** 梯度同向性分析
- 图：$\cos(g_{\text{trigger}}, g_{\text{clean}})$ 分布
- 结论：BadCLIP++ 的梯度同向性是 rebound 的直接原因

### 15.3 Method Section 组织

```
Section 4: BasinBreaker
  4.1 Overview（三阶段流程图）
  4.2 Suspect Backdoor Subspace Identification
      - Gradient-difference SVD（主方案）
      - Suspect score 定义
  4.3 Basin-Breaking via Orthogonal Sharpness Ascent
      - 数学定义
      - 正交化约束
      - Subspace Reset
  4.4 Stability-constrained Recovery
      - 优化目标
      - Layer-wise freeze
  4.5 Anti-rebound Training
      - 一阶近似推导
      - 与 BadCLIP++ 梯度同向性的理论联系
  4.6 Complete Algorithm（伪代码）
```

### 15.4 Evaluation Section 组织

```
Section 5: Experiments
  5.1 Setup（模型、数据、攻击、baseline、指标）
  5.2 Main Results（当前 ASR + CA 表格）
  5.3 Persistence Evaluation（Rebound Curve + AURC + LHPS 表格）
      ← 这是本文最重要的实验
  5.4 Cross-model / Cross-attack Generalization
  5.5 Ablation Study
  5.6 Analysis（曲率变化、梯度同向性变化、子空间可视化）
```

### 15.5 Theory / Analysis Section 组织

```
Section 6: Theoretical Analysis
  6.1 Why Persistent Backdoors Survive Clean FT（Proposition 1）
  6.2 Why Basin-Breaking Reduces Rebound（Proposition 2）
  6.3 Why Anti-rebound Breaks Gradient Co-directionality（Proposition 3）
  6.4 Rebound Upper Bound（Theorem 1）
  6.5 Empirical Verification
```

### 15.6 Discussion 应该强调什么

1. **对现有防御评估标准的挑战：** 只看当前 ASR 不够，必须评估 rebound
2. **对 BadCLIP++ 安全声明的回应：** BasinBreaker 证明持久性后门并非不可防御
3. **参数几何视角的通用性：** 这一视角不限于 CLIP，可能适用于其他模型
4. **负责任披露：** 我们的 rebound 发现揭示了现有防御的不足，已通知相关作者

### 15.7 Limitations 如何写得不削弱贡献

**写法原则：** 每个 limitation 后面跟一个"但这不影响核心贡献"的说明。

- "Hessian 估计在超大模型上成本较高"→"但我们提供了 gradient-difference 轻量替代方案，且 CLIP 规模模型完全可行"
- "理论分析基于局部二阶近似"→"但经验验证与理论预测一致，且这是后门防御领域首个 rebound bound"
- "主要在 CLIP 架构上验证"→"但 CLIP 是当前多模态后门研究的标准 testbed，且我们在 3 种不同架构上验证了泛化性"
- "Anti-rebound 不能保证无限 horizon 的稳定性"→"但 50 epoch 已覆盖绝大多数现实 fine-tuning 场景"

### 15.8 论文标题备选

1. **BasinBreaker: Curvature-Aware Subspace Purification against Persistent Multimodal Backdoors**（推荐）
2. **Breaking the Basin: Persistence-Aware Defense for Multimodal Contrastive Learning Backdoors**
3. **Beyond Instant Purification: Curvature-Aware Defense against Rebound-Resilient Multimodal Backdoors**
4. **No More Rebound: Geometry-Driven Defense for Persistent Backdoors in Vision-Language Models**

### 15.9 摘要草稿

> Multimodal contrastive learning models such as CLIP are vulnerable to backdoor attacks. While existing defenses can reduce the attack success rate (ASR) immediately after purification, we reveal a critical yet overlooked threat: **persistent backdoors rebound** after subsequent clean fine-tuning. We show that state-of-the-art defenses (CleanCLIP, InverTune, FT-SAM) suffer from ASR rebound of 20-60% within 50 epochs of clean fine-tuning when facing persistent attacks like BadCLIP++. We trace this vulnerability to the backdoor parameters residing in **low-curvature, wide basins** in the parameter space, where clean fine-tuning gradients fail to escape. Based on this analysis, we propose **BasinBreaker**, the first persistence-aware defense that (1) identifies the suspect backdoor subspace via gradient-difference analysis, (2) breaks the backdoor basin through orthogonal sharpness ascent, (3) reprojects parameters away from the suspect subspace, and (4) explicitly minimizes rebound risk via an anti-rebound training objective that counteracts the gradient co-directionality exploited by persistent attacks. We also introduce a comprehensive **Persistence Evaluation Protocol** with new metrics including Rebound ASR and Area Under Rebound Curve (AURC). Experiments on 3 model architectures, 4 attack types, and 6 post-defense adaptation scenarios demonstrate that BasinBreaker achieves ≤5% Rebound ASR while maintaining clean accuracy, significantly outperforming all baselines.

### 15.10 Contributions Bullet Points

1. **New Threat Characterization：** 我们系统揭示了持久性多模态后门的 rebound 现象，证明现有防御提供的是虚假安全感。
2. **Geometric Analysis：** 我们从参数几何角度解释了 rebound 的根源——低曲率后门盆地和梯度同向性，并给出了 rebound upper bound。
3. **BasinBreaker Defense：** 我们提出首个 persistence-aware 防御框架，通过曲率感知子空间识别、正交锐度上升、子空间重投影和 anti-rebound 训练实现长期稳定净化。
4. **Persistence Evaluation Protocol：** 我们提出首个系统性的后门持久性评估协议，包括 Rebound ASR、AURC、LHPS 等指标。
5. **Comprehensive Evaluation：** 在 3 种模型、4 种攻击、6 种防御、6 种后续适配条件下的全面验证。
