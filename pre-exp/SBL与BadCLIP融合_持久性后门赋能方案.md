# SBL × BadCLIP 融合方案：通用持久性后门训练模块设计

生成日期：2026-05-06
研究目标：将 SBL（Sequential Backdoor Learning）的持久性赋能思路与 BadCLIP 等非持久性后门攻击方法融合，设计通用的持久性后门训练模块

---

## 0. 研究动机与问题定义

### 0.1 当前困境

做多模态持久性后门**防御**研究时面临一个关键瓶颈：攻击 baseline 不足。目前系统性的多模态持久性后门攻击工作仅有 BadCLIP++（尚未发表），单一的攻击方法不足以支撑防御工作的全面评估。

### 0.2 核心思路

SBL（ECCV 2024）已经证明了一个关键结论：**任何非持久性后门攻击都可以通过 SAM + 持续学习（CL）正则化的两阶段训练获得持久性**。但 SBL 仅在单模态分类任务（CIFAR-10, GTSRB, ImageNet-10）上的简单攻击（BadNets, Blended, SIG, Dynamic）上验证过。

我们的目标是：
1. 将 SBL 的思想迁移到多模态对比学习（CLIP）场景
2. 首先以 BadCLIP 为基线攻击方法验证可行性
3. 设计通用的持久性赋能模块，使其能与任意多模态后门攻击方法组合

### 0.3 为什么这不是简单地"套用 SBL"

SBL → CLIP 的迁移面临以下根本性差异，不能简单移植：

| 维度 | SBL（原始场景） | CLIP/多模态场景 |
|------|---------------|---------------|
| 任务类型 | 图像分类（单模态） | 图文对比学习（多模态） |
| 损失函数 | Cross-Entropy | InfoNCE（对称对比损失） |
| 模型结构 | 单一分类器（ResNet18） | 双编码器（Visual + Text Encoder） |
| 优化器 | SGD | AdamW（CLIP 标准） |
| 学习率量级 | 0.01（从头训练级别） | 1e-6（大模型微调级别） |
| 数据规模 | ~50K 样本 | ~500K 图文对 |
| 投毒率 | 10% | 0.3%（1500/500K） |
| 后门机制 | 简单 patch/blend → 标签映射 | 双嵌入引导 → 跨模态语义映射 |
| 评估方式 | 分类准确率 + ASR | 零样本分类 CA + ASR、线性探测、检索 |
| 防御方式 | SGD/SAM/NAD 微调 | CleanCLIP（跨模态+模态内对比损失） |

这些差异意味着需要重新设计 SAM 的应用方式、CL 正则化的计算方式、以及训练调度策略。

---

## 1. BadCLIP 与 SBL 的核心机制深度分析

### 1.1 BadCLIP 核心机制回顾

BadCLIP 的三阶段流水线：

**Stage 1：触发器优化**（`embeding_optimize_patch.py`）
- 冻结 CLIP 模型，仅优化 patch 像素
- 优化目标：使带触发器的图像在嵌入空间中同时接近目标文本嵌入（$\mathcal{L}_t$）和目标视觉嵌入（$\mathcal{L}_i^p + \mathcal{L}_i^n$）
- 优化器：Adam，50 epochs，batch_size=64
- 核心损失：
$$\mathcal{L} = \mathcal{L}_t + \lambda_1 \times \max(0, \mathcal{L}_i^p + \lambda_2 \times \mathcal{L}_i^n + \eta)$$

其中 $\mathcal{L}_t$ 是 InfoNCE 对比损失（触发图像 vs 目标文本），$\mathcal{L}_i^p$ 是三元组正样本损失（触发图像 → 真实目标类图像），$\mathcal{L}_i^n$ 是三元组负样本损失（触发图像 ↛ 原始干净图像）。

**Stage 2：投毒数据生成**（`create_backdoor_data.py`）
- 从 500K CC3M 数据中选取 1500 个样本添加触发器
- 替换文本描述为目标类的自然描述
- 输出：混合数据集（500K，含 1500 投毒样本）

**Stage 3：后门训练**（`train.py`）
- 在混合数据集上微调 CLIP
- 优化器：AdamW，lr=1e-6，10 epochs，batch_size=128
- 损失：标准 CLIP 对称 InfoNCE 对比损失
$$\mathcal{L}_{CLIP} = \frac{1}{2}[\text{CE}(\text{logit\_scale} \cdot \mathbf{I} \cdot \mathbf{T}^T, \text{target}) + \text{CE}(\text{logit\_scale} \cdot \mathbf{T} \cdot \mathbf{I}^T, \text{target})]$$

**关键代码细节（来自代码仓库分析）：**
- 学习率调度：余弦退火 + 线性预热（10K steps）
- 混合精度训练：使用 `torch.cuda.amp.GradScaler`
- `logit_scale` 参数被 clamp 到 $[0, \ln(100)]$
- AdamW 的两组参数：BN/LN/bias/logit_scale 无 weight_decay，其余有 weight_decay

### 1.2 SBL 核心机制回顾

SBL 的两步训练框架：

**Step 0：SAM 后门训练**
- 数据：$\mathcal{D}_0$（85% 混合数据 = 干净 + 投毒）
- 优化器：SGD + SAM wrapper，lr=0.01
- Epochs：150
- 目标：在**平坦**的后门损失区域找到最优解 $\theta_{B_0}$
$$\theta_{B_0} = \arg\min_\theta \mathcal{L}^{SAM}(\mathcal{D}_0; \theta)$$

SAM 的核心操作（`sam.py`）：
```
每个 batch：
  1. 前向+反向，计算梯度 g
  2. first_step: 保存原参数 w，移动到 w + ρ·g/||g||（上升到局部最大值）
  3. 在扰动点重新前向+反向
  4. second_step: 恢复到 w，用扰动点的梯度做更新
```

**Step 1：CL 约束微调**
- 数据：$\mathcal{D}_1$（10% 纯干净数据）
- 优化器：标准 SGD，lr=0.001（比 Step 0 低一个数量级）
- Epochs：100
- 目标：在不遗忘后门的前提下适应干净数据
$$\theta_B = \arg\min_\theta \mathcal{L}(\mathcal{D}_1; \theta) + \mathcal{R}(\theta_{B_0}, \theta)$$

CL 正则化 $\mathcal{R}$ 的三种实现：
- **EWC**：$\mathcal{R} = \lambda \sum_i F_i (\theta_i - \theta_{B_0,i})^2$，其中 $F_i$ 是 Fisher 信息矩阵对角近似
- **Anchoring**：$\mathcal{R} = \lambda \cdot \text{mean}_{clean}(||\text{softmax}(f_{\theta_{B_0}}(x)) - \text{softmax}(f_\theta(x))||^2)$
- **A-GEM**：不加正则项，但投影梯度以避免与 Task 0 梯度冲突

**关键代码细节（来自代码仓库分析）：**
- SAM 仅用于 Step 0，Step 1 切换为普通 SGD（`args.opt_mode = 'normal'`）
- EWC 的 Fisher 信息在 `end_task()` 中计算：遍历所有样本，累积 $F += \text{grad}^2$
- Anchoring 的锚定模型在 `end_task()` 中通过 `deepcopy` 保存
- A-GEM 存储 replay buffer，计算梯度投影：若 $g_{current} \cdot g_{buffer} < 0$，则 $g' = g_{current} - \frac{g_{current} \cdot g_{buffer}}{||g_{buffer}||^2} g_{buffer}$

### 1.3 两者的互补性分析

```
BadCLIP 的优势：                          BadCLIP 的不足：
✓ 精心设计的触发器（双嵌入引导）            ✗ 标准微调训练，无持久性设计
✓ 对检测防御有抵抗力（参数偏移小）           ✗ CleanCLIP 后 ASR 从 98.81% → 89.60%
✓ 在下游任务（Linear Probe）中有效           ✗ 无 flat minima 保证
✓ 跨域防御仍有 87.21% ASR                  ✗ 更强防御 + 更多 epoch 可能进一步降低

SBL 的优势：                              SBL 的不足：
✓ 使任意攻击获得持久性（100% ASR 抵抗 NAD/FT-SAM）  ✗ 仅在单模态分类上验证
✓ 平坦损失景观 → 防御者梯度范数小            ✗ 未涉及对比学习损失
✓ 通用框架，与具体攻击解耦                  ✗ 未涉及多模态/CLIP
✓ 多种 CL 方法可选                         ✗ 未验证极低投毒率（0.3%）场景
```

**互补性结论**：BadCLIP 提供了高质量的多模态触发器设计和投毒策略，SBL 提供了使任意后门获得持久性的训练框架。两者的结合应该能产出**既难以检测又难以通过微调清除**的多模态持久性后门。

---

## 2. SBL × BadCLIP 融合设计

### 2.1 融合架构总览

融合后的方法（暂称 **SBL-BadCLIP**）保留 BadCLIP 的三阶段流水线，但将 Stage 3 替换为 SBL 风格的两步训练：

```
┌─────────────────────────────────────────────────────────────┐
│                    SBL-BadCLIP Pipeline                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Stage 1: Trigger Optimization (来自 BadCLIP, 不变)          │
│  ┌─────────────────────────────────────────────┐            │
│  │ 冻结 CLIP → 优化 patch → L_t + L_i^p + L_i^n │            │
│  │ Adam, 50 epochs, patch_size=16               │            │
│  └──────────────────────┬──────────────────────┘            │
│                         ▼                                   │
│  Stage 2: Poisoned Data Generation (来自 BadCLIP, 不变)      │
│  ┌─────────────────────────────────────────────┐            │
│  │ 500K CC3M, 1500 poisoned, 自然文本替换        │            │
│  └──────────────────────┬──────────────────────┘            │
│                         ▼                                   │
│  Stage 3: SBL-style Two-Step Training (★ 核心修改)          │
│  ┌─────────────────────────────────────────────┐            │
│  │ Step 0: SAM-Backdoor Training                │            │
│  │   数据: D_0 (425K mixed, 含 1500 poisoned)    │            │
│  │   优化器: AdamW + SAM wrapper                 │            │
│  │   损失: InfoNCE contrastive loss              │            │
│  │   lr: 5e-6, epochs: 10-15                    │            │
│  │   → 得到 θ_B0 (平坦后门区域)                  │            │
│  ├─────────────────────────────────────────────┤            │
│  │ Transition: end_task()                       │            │
│  │   计算 Fisher/保存锚模型/构建 replay buffer   │            │
│  ├─────────────────────────────────────────────┤            │
│  │ Step 1: CL-Constrained Clean Fine-tuning     │            │
│  │   数据: D_1 (50K clean image-text pairs)      │            │
│  │   优化器: AdamW (无 SAM)                      │            │
│  │   损失: InfoNCE + CL regularization           │            │
│  │   lr: 5e-7, epochs: 5-10                     │            │
│  │   → 得到 θ_B (持久性后门模型)                  │            │
│  └─────────────────────────────────────────────┘            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 关键适配设计

#### 2.2.1 SAM for AdamW（适配 CLIP 优化器）

SBL 原始实现中 SAM 包装的是 SGD。对于 CLIP 微调，需要包装 AdamW：

```python
class SAM_AdamW:
    """SAM wrapper for AdamW optimizer, adapted for CLIP fine-tuning."""
    
    def __init__(self, params, base_optimizer_cls=torch.optim.AdamW, 
                 rho=0.05, **kwargs):
        # kwargs 传递给 AdamW: lr, betas, eps, weight_decay
        self.base_optimizer = base_optimizer_cls(params, **kwargs)
        self.rho = rho
        self.param_groups = self.base_optimizer.param_groups
    
    def first_step(self, zero_grad=False):
        """上升到局部最大值：w + ε, 其中 ε = ρ * grad / ||grad||"""
        grad_norm = self._grad_norm()
        for group in self.param_groups:
            scale = self.rho / (grad_norm + 1e-12)
            for p in group["params"]:
                if p.grad is None:
                    continue
                # 保存原始参数
                self.state[p]["old_p"] = p.data.clone()
                # 上升步
                e_w = p.grad * scale
                p.add_(e_w)
        if zero_grad:
            self.zero_grad()
    
    def second_step(self, zero_grad=False):
        """恢复到原始参数，用扰动点梯度做 AdamW 更新"""
        for group in self.param_groups:
            for p in group["params"]:
                if p.grad is None:
                    continue
                p.data = self.state[p]["old_p"]  # 恢复
        self.base_optimizer.step()  # AdamW 更新
        if zero_grad:
            self.zero_grad()
```

**关键考量**：
- CLIP 微调的 lr 极低（1e-6 量级），SAM 的 $\rho$ 参数需要相应调小（建议 $\rho = 0.01 \sim 0.05$，原 SBL 使用 $\rho = 0.05$）
- AdamW 有自适应学习率，SAM 的扰动是基于梯度范数的，两者的交互需要实验验证
- CLIP 有 `logit_scale` 参数，SAM 扰动可能需要排除此参数（或单独设 $\rho$）

#### 2.2.2 InfoNCE 下的 EWC Fisher 信息计算

原 SBL 的 EWC Fisher 信息基于分类 CE 损失的梯度计算。对于 CLIP 的 InfoNCE 损失，计算方式需要适配：

```python
def compute_fisher_clip(model, dataloader, device):
    """
    计算 CLIP 模型在 InfoNCE 损失下的 Fisher 信息矩阵（对角近似）。
    与分类任务的 Fisher 不同，这里基于对比损失的梯度。
    """
    fisher = {n: torch.zeros_like(p) for n, p in model.named_parameters() 
              if p.requires_grad}
    
    model.eval()
    n_samples = 0
    
    for batch in dataloader:
        images, texts = batch["image"].to(device), batch["text"].to(device)
        
        model.zero_grad()
        
        # 前向传播
        image_embeds = model.encode_image(images)
        text_embeds = model.encode_text(texts)
        
        # 归一化
        image_embeds = F.normalize(image_embeds, dim=-1)
        text_embeds = F.normalize(text_embeds, dim=-1)
        
        # InfoNCE 损失
        logit_scale = model.logit_scale.exp()
        logits = logit_scale * image_embeds @ text_embeds.t()
        target = torch.arange(len(images), device=device)
        loss = (F.cross_entropy(logits, target) + 
                F.cross_entropy(logits.t(), target)) / 2
        
        loss.backward()
        
        for n, p in model.named_parameters():
            if p.requires_grad and p.grad is not None:
                fisher[n] += p.grad.data.pow(2) * len(images)
        
        n_samples += len(images)
    
    # 归一化
    for n in fisher:
        fisher[n] /= n_samples
    
    return fisher
```

**设计考量**：
- Fisher 信息在整个 $\mathcal{D}_0$（混合数据）上计算，包含干净和投毒样本
- 这确保了 Fisher 同时反映干净特征和后门特征的重要性
- 对于 CLIP 的双编码器，Fisher 自然覆盖了 visual encoder 和 text encoder 的所有参数

#### 2.2.3 Anchoring for CLIP

SBL 原始 Anchoring 使用分类 softmax 输出的 KL 散度。对于 CLIP，我们用**相似度矩阵**作为锚定目标：

```python
class AnchoringCLIP:
    """
    Anchoring regularization for CLIP.
    锚定目标：Step 0 结束时 CLIP 模型的图文相似度分布。
    """
    
    def __init__(self, model, lambda_anchor=1.0):
        self.anchor_model = copy.deepcopy(model)
        self.anchor_model.eval()
        for p in self.anchor_model.parameters():
            p.requires_grad = False
        self.lambda_anchor = lambda_anchor
    
    def penalty(self, images, texts, model):
        """
        计算当前模型与锚模型在相似度分布上的偏差。
        仅在干净样本上计算（如果能区分的话）。
        """
        with torch.no_grad():
            anchor_img = self.anchor_model.encode_image(images)
            anchor_txt = self.anchor_model.encode_text(texts)
            anchor_img = F.normalize(anchor_img, dim=-1)
            anchor_txt = F.normalize(anchor_txt, dim=-1)
            anchor_logits = anchor_img @ anchor_txt.t()
        
        current_img = model.encode_image(images)
        current_txt = model.encode_text(texts)
        current_img = F.normalize(current_img, dim=-1)
        current_txt = F.normalize(current_txt, dim=-1)
        current_logits = current_img @ current_txt.t()
        
        # 锚定：保持相似度分布一致
        loss = F.mse_loss(current_logits, anchor_logits)
        
        return self.lambda_anchor * loss
```

#### 2.2.4 数据划分策略

```
原始 BadCLIP 数据: 500K CC3M 图文对 (含 1500 poisoned)
                     │
    ┌────────────────┼────────────────┐
    ▼                ▼                ▼
  D_0 (混合)       D_1 (干净)      D_defense (评估)
  425K             50K              25K
  含 1500 poisoned  纯干净           纯干净
  用于 Step 0       用于 Step 1       用于防御评估
  (85%)            (10%)            (5%)
```

**比例选择的理由**：
- 沿用 SBL 的 85/10/5 比例，已经在多种设置下验证有效
- 425K 的混合数据仍然保持 0.35% 的极低投毒率，不影响 BadCLIP 的隐蔽性
- 50K 的干净数据足够做 CL 约束微调（模拟防御者的 clean fine-tuning）

### 2.3 训练超参数设计

| 参数 | Step 0 (SAM-Backdoor) | Step 1 (CL-Clean FT) | 设计理由 |
|------|----------------------|----------------------|---------|
| 优化器 | AdamW + SAM | AdamW (无 SAM) | CLIP 标准优化器；Step 1 不需要 SAM |
| 学习率 | 5e-6 | 5e-7 | CLIP 微调需要小 lr；Step 1 比 Step 0 低一个数量级（SBL 的 0.01→0.001 比例） |
| SAM ρ | 0.01~0.05 | N/A | 因 CLIP lr 小，ρ 也需相应调整 |
| Epochs | 10~15 | 5~10 | BadCLIP 原始用 10 epochs；Step 1 无需太多 |
| Batch size | 128 | 128 | 保持与 BadCLIP 一致 |
| Weight decay | 0.1 | 0.1 | AdamW 标准设置 |
| Warmup steps | 10000 | 50~500 | Step 0 沿用 BadCLIP；Step 1 短预热 |
| CL λ (EWC/Anchor) | N/A | 0.1~10.0 | 需要网格搜索；CLIP 损失量级与 CE 不同 |
| 混合精度 | 是 | 是 | 保持与 BadCLIP 一致 |

### 2.4 完整训练算法伪代码

```
Algorithm: SBL-BadCLIP Training

Input: 
  - Pretrained CLIP model θ_0
  - Optimized trigger δ_v (from BadCLIP Stage 1)
  - Mixed dataset D_0 (425K, with 1500 poisoned)
  - Clean dataset D_1 (50K)
  - CL method ∈ {EWC, Anchoring, A-GEM}

Output: Persistent backdoored CLIP model θ_B

// ==================== Step 0: SAM-Backdoor Training ====================
Initialize θ ← θ_0
optimizer ← SAM_AdamW(θ, lr=5e-6, rho=0.05)
scheduler ← CosineAnnealingWithWarmup(warmup=10000)

for epoch in 1..15:
    for (images, texts) in D_0:
        // ---- SAM First Step ----
        enable_running_stats(θ)
        img_emb = normalize(encode_image(images; θ))
        txt_emb = normalize(encode_text(texts; θ))
        loss = InfoNCE(img_emb, txt_emb, θ.logit_scale)
        loss.backward()
        optimizer.first_step(zero_grad=True)
        
        // ---- SAM Second Step ----
        disable_running_stats(θ)
        img_emb = normalize(encode_image(images; θ))  // 在扰动点重新计算
        txt_emb = normalize(encode_text(texts; θ))
        loss = InfoNCE(img_emb, txt_emb, θ.logit_scale)
        loss.backward()
        optimizer.second_step(zero_grad=True)
        
        clamp(θ.logit_scale, 0, ln(100))
        scheduler.step()

θ_B0 ← θ  // 保存 Step 0 的模型

// ==================== Transition: end_task() ====================
if CL_method == EWC:
    Fisher ← compute_fisher_clip(θ_B0, D_0)
    checkpoint ← deepcopy(θ_B0.parameters())
elif CL_method == Anchoring:
    anchor_model ← deepcopy(θ_B0)
elif CL_method == A-GEM:
    buffer ← sample_replay_buffer(D_0, buffer_size=5000)

// ==================== Step 1: CL-Constrained Clean Fine-tuning ===========
optimizer ← AdamW(θ, lr=5e-7)  // 无 SAM，更低 lr
scheduler ← CosineAnnealingWithWarmup(warmup=500)

for epoch in 1..10:
    for (images, texts) in D_1:
        img_emb = normalize(encode_image(images; θ))
        txt_emb = normalize(encode_text(texts; θ))
        L_clean = InfoNCE(img_emb, txt_emb, θ.logit_scale)
        
        // ---- CL Regularization ----
        if CL_method == EWC:
            L_reg = λ * Σ_i Fisher[i] * (θ[i] - checkpoint[i])^2
        elif CL_method == Anchoring:
            L_reg = λ * anchoring_penalty(images, texts, θ, anchor_model)
        elif CL_method == A-GEM:
            L_reg = 0  // A-GEM 通过梯度投影实现
        
        loss = L_clean + L_reg
        loss.backward()
        
        if CL_method == A-GEM:
            project_gradients(θ, buffer)  // 投影以避免冲突
        
        optimizer.step()
        clamp(θ.logit_scale, 0, ln(100))
        scheduler.step()

θ_B ← θ  // 最终持久性后门模型
return θ_B
```

### 2.5 预期效果分析

**为什么 SBL-BadCLIP 应该比原始 BadCLIP 更持久？**

1. **SAM 使后门参数落入平坦区域**：Step 0 的 SAM 训练确保模型收敛到的后门区域具有低曲率，这意味着 clean fine-tuning（CleanCLIP 等）的梯度更新不容易将模型推出后门区域。

2. **CL 正则化模拟了防御过程**：Step 1 用纯干净数据微调（模拟防御者的行为），同时通过 CL 约束防止后门被遗忘。这让模型"预习"了防御过程，减少了未来防御的效果。

3. **双嵌入引导 + 平坦景观的协同**：BadCLIP 的触发器已经在嵌入空间中与目标语义对齐，SAM 的平坦景观进一步确保这种对齐不会因微调而被破坏。

**预期数值改善**：

| 场景 | BadCLIP 原始 ASR | SBL-BadCLIP 预期 ASR |
|------|----------------|---------------------|
| No Defense | 98.81% | ~98.5%（基本持平） |
| FT (标准微调) | 92.50% | ~96-98% |
| CleanCLIP | 89.60% | ~94-97% |
| CleanCLIP + 更多 epoch | ~70-80%（估计） | ~88-93% |
| Linear Probe | 99.14%/66.40% | ~99%/~80-90% |

---

## 3. Loss Landscape 可视化验证方案

### 3.1 可视化目标

验证 SBL-BadCLIP 是否确实将后门参数推入了平坦区域，需要设计以下可视化：

1. **线性插值图**（Linear Interpolation）：在后门模型 $\theta_B$ 和防御后模型 $\theta_F$ 之间线性插值，观察 clean loss/accuracy 和 poison loss/ASR 的变化
2. **2D 损失景观图**（2D Loss Landscape）：在后门模型附近的参数空间二维切面上绘制损失曲面
3. **梯度范数图**（Gradient Norm During Defense）：在防御微调过程中跟踪梯度范数变化

### 3.2 线性插值可视化（对标 SBL 论文 Figure 1 & 2）

```python
def linear_interpolation_clip(model_start, model_end, test_loader, 
                               trigger_fn, n_points=21):
    """
    在两个 CLIP 模型之间线性插值，评估中间模型的 clean/poison 性能。
    
    对标 SBL 论文 Fig. 1(b)(d) 和 Fig. 2 的所有列。
    """
    results = {
        'alpha': [],
        'clean_loss': [], 'clean_acc': [],
        'poison_loss': [], 'poison_asr': []
    }
    
    alphas = np.linspace(0, 1, n_points)
    
    # 获取参数字典
    params_start = {n: p.data for n, p in model_start.named_parameters()}
    params_end = {n: p.data for n, p in model_end.named_parameters()}
    
    # 创建中间模型
    interp_model = copy.deepcopy(model_start)
    
    for alpha in alphas:
        # 线性插值: θ(α) = (1-α)·θ_start + α·θ_end
        for n, p in interp_model.named_parameters():
            p.data = (1 - alpha) * params_start[n] + alpha * params_end[n]
        
        # 评估 clean 性能 (零样本分类)
        clean_loss, clean_acc = evaluate_zeroshot(interp_model, test_loader)
        
        # 评估 poison 性能 (带触发器的零样本分类)
        poison_loss, poison_asr = evaluate_asr(interp_model, test_loader, trigger_fn)
        
        results['alpha'].append(alpha)
        results['clean_loss'].append(clean_loss)
        results['clean_acc'].append(clean_acc)
        results['poison_loss'].append(poison_loss)
        results['poison_asr'].append(poison_asr)
    
    return results
```

**需要生成的插值图（共 4 组对比，每组 4 条曲线）**：

```
                 BadCLIP (原始)              SBL-BadCLIP (融合)
              ┌─────────────────┐        ┌─────────────────┐
 θ_B → θ_F   │ Clean loss ─    │        │ Clean loss ─    │
 (后门→防御)  │ Clean acc  ─    │        │ Clean acc  ─    │
              │ Poison loss ─   │        │ Poison loss ─   │
              │ ASR        ─    │        │ ASR        ─    │
              │                 │        │                 │
              │ ASR 应急剧下降   │        │ ASR 应保持高位   │
              └─────────────────┘        └─────────────────┘

              ┌─────────────────┐        ┌─────────────────┐
 θ_B0 → θ_B  │      N/A        │        │ Clean loss ─    │
 (Step0→Step1)│  (无此阶段)      │        │ Clean acc  ─    │
              │                 │        │ Poison loss ─   │
              │                 │        │ ASR        ─    │
              │                 │        │                 │
              │                 │        │ 低误差路径连接    │
              └─────────────────┘        └─────────────────┘
```

### 3.3 2D 损失景观可视化

基于 SBL 的 `utils/loss_landscape.py`，适配 CLIP：

```python
def loss_landscape_2d_clip(model, dataloader, trigger_fn, 
                           n_x=21, n_y=21, range_val=1.0):
    """
    在模型参数空间的二维随机切面上计算损失景观。
    
    使用 filter-normalized random directions (Li et al., 2018)。
    """
    # 1. 生成两个随机方向 d1, d2
    d1, d2 = create_normalized_bases(model)
    
    # 2. 网格
    xs = np.linspace(-range_val, range_val, n_x)
    ys = np.linspace(-range_val, range_val, n_y)
    
    # 3. 保存原始参数
    origin_params = {n: p.data.clone() for n, p in model.named_parameters()}
    
    landscape = {
        'clean_loss': np.zeros((n_x, n_y)),
        'poison_loss': np.zeros((n_x, n_y)),
        'clean_acc': np.zeros((n_x, n_y)),
        'poison_asr': np.zeros((n_x, n_y)),
    }
    
    for i, alpha in enumerate(xs):
        for j, beta in enumerate(ys):
            # θ' = θ_0 + α·d1 + β·d2
            for n, p in model.named_parameters():
                p.data = origin_params[n] + alpha * d1[n] + beta * d2[n]
            
            # 评估
            cl, ca = evaluate_zeroshot(model, dataloader)
            pl, pa = evaluate_asr(model, dataloader, trigger_fn)
            
            landscape['clean_loss'][i, j] = cl
            landscape['poison_loss'][i, j] = pl
            landscape['clean_acc'][i, j] = ca
            landscape['poison_asr'][i, j] = pa
    
    # 恢复参数
    for n, p in model.named_parameters():
        p.data = origin_params[n]
    
    return landscape, xs, ys
```

**可视化输出**：

生成以下对比图（2×2 布局）：

| | BadCLIP (原始) | SBL-BadCLIP (融合) |
|---|---|---|
| **Poison Loss 等高线** | 窄谷（sharp minimum） | 宽盆地（flat basin） |
| **ASR 等高线** | ASR 高值区域小 | ASR 高值区域大（平坦） |

每个等高线图叠加两个标记：$\theta_B$（后门模型）和 $\theta_F$（防御后模型）的投影位置。

### 3.4 梯度范数跟踪可视化（对标 SBL 论文 Figure 3）

```python
def track_gradient_norm_during_defense(model, clean_dataloader, 
                                        defense_epochs=50, lr=1e-5):
    """
    在 CleanCLIP 防御微调过程中，记录每个 step 的梯度范数。
    对比 BadCLIP 原始 vs SBL-BadCLIP。
    """
    grad_norms = []
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    
    for epoch in range(defense_epochs):
        for batch in clean_dataloader:
            optimizer.zero_grad()
            loss = compute_cleanclip_loss(model, batch)
            loss.backward()
            
            # 记录总梯度范数
            total_norm = 0.0
            for p in model.parameters():
                if p.grad is not None:
                    total_norm += p.grad.data.norm(2).item() ** 2
            total_norm = total_norm ** 0.5
            grad_norms.append(total_norm)
            
            optimizer.step()
    
    return grad_norms
```

**预期结果**：
- BadCLIP 原始模型：防御初期梯度范数较大，模型被快速推出后门区域
- SBL-BadCLIP 模型：防御过程中梯度范数始终较小（平坦区域 → 梯度小），模型难以逃离后门区域

### 3.5 可视化图表汇总

| 图编号 | 内容 | 对标 SBL 论文 | 目的 |
|-------|------|-------------|------|
| Fig.1 | 线性插值（θ_B → θ_F）：BadCLIP 原始 vs SBL-BadCLIP | Fig.1(b)(d), Fig.2 col1/3 | 验证 SBL-BadCLIP 的后门区域更难逃离 |
| Fig.2 | 线性插值（θ_B0 → θ_B）：SBL-BadCLIP 内部 | Fig.2 col2 | 验证 Step 0 → Step 1 存在低误差路径 |
| Fig.3 | 2D 损失景观：Poison Loss 等高线对比 | 拓展（SBL 无此图） | 直观展示 flat basin |
| Fig.4 | 2D 损失景观：ASR 等高线对比 | 拓展 | 直观展示 ASR 高值区域范围 |
| Fig.5 | 梯度范数跟踪：防御微调过程 | Fig.3 | 验证 SBL-BadCLIP 在防御时梯度更小 |
| Fig.6 | ASR 随防御 epoch 数变化曲线 | 拓展 | 展示长时间防御下的持久性 |

---

## 4. 通用持久性后门训练模块设计

### 4.1 设计理念

目标：设计一个**与具体后门攻击方法解耦**的通用持久性赋能模块，使任意多模态后门攻击方法（BadCLIP, BadNet-CLIP, Blended-CLIP, TrojVQA 等）都能通过简单组合获得持久性。

核心原则：
1. **攻击无关**：不修改原始攻击方法的触发器设计或投毒策略
2. **模型无关**：支持不同的 CLIP 架构（RN50, RN101, ViT-B/32 等）
3. **损失无关**：通过抽象接口支持不同的训练损失（InfoNCE, CE, 混合损失等）
4. **即插即用**：只需包装原始训练循环，不改变模型结构

### 4.2 模块架构

```
┌─────────────────────────────────────────────────────────┐
│              PersistentBackdoorTrainer                    │
│              (通用持久性后门训练模块)                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────┐  ┌──────────────────┐              │
│  │  SAM Wrapper     │  │  CL Regularizer  │              │
│  │  ─────────────   │  │  ──────────────  │              │
│  │  wrap(optimizer)  │  │  EWC / Anchor /  │              │
│  │  first_step()    │  │  AGEM / Naive    │              │
│  │  second_step()   │  │  end_task()      │              │
│  │  supports: SGD,  │  │  penalty()       │              │
│  │  Adam, AdamW     │  │  project_grad()  │              │
│  └─────────────────┘  └──────────────────┘              │
│                                                         │
│  ┌─────────────────┐  ┌──────────────────┐              │
│  │  Data Splitter   │  │  Training        │              │
│  │  ─────────────   │  │  Scheduler       │              │
│  │  split(D, ratio) │  │  ──────────────  │              │
│  │  → D_0, D_1, D_d │  │  manage epochs   │              │
│  │                   │  │  switch optimizer│              │
│  │                   │  │  switch lr       │              │
│  └─────────────────┘  └──────────────────┘              │
│                                                         │
│  ┌──────────────────────────────────────────┐           │
│  │  Loss Landscape Analyzer                  │           │
│  │  ────────────────────────                 │           │
│  │  linear_interpolation()                   │           │
│  │  loss_landscape_2d()                      │           │
│  │  gradient_norm_tracking()                 │           │
│  │  generate_report()                        │           │
│  └──────────────────────────────────────────┘           │
│                                                         │
│  Interface:                                             │
│  ─────────                                              │
│  trainer = PersistentBackdoorTrainer(                    │
│      attack_method="badclip",  # or "badnet", "blended" │
│      cl_method="ewc",          # or "anchor", "agem"    │
│      sam_rho=0.05,                                      │
│      cl_lambda=1.0,                                     │
│      split_ratio=[0.85, 0.10, 0.05],                    │
│  )                                                      │
│  trainer.train(model, dataset, loss_fn)                  │
│  trainer.visualize(model_before, model_after)            │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 4.3 核心接口设计

```python
class PersistentBackdoorTrainer:
    """
    通用持久性后门训练模块。
    
    将任意后门攻击方法的标准训练流程替换为 SBL 风格的两步训练。
    不修改攻击方法本身（触发器设计、投毒策略），只改变训练方式。
    """
    
    def __init__(self, 
                 cl_method='ewc',        # 'ewc', 'anchoring', 'agem', 'naive'
                 sam_rho=0.05,           # SAM 扰动半径
                 cl_lambda=1.0,          # CL 正则化强度
                 split_ratio=(0.85, 0.10, 0.05),  # 混合/干净/防御 数据比例
                 step0_lr_scale=1.0,     # Step 0 学习率倍数（相对于原始 lr）
                 step1_lr_scale=0.1,     # Step 1 学习率倍数
                 step0_epochs=None,      # Step 0 epochs (None = 使用原始值)
                 step1_epochs=None,      # Step 1 epochs
                 ):
        self.cl_method = cl_method
        self.sam_rho = sam_rho
        self.cl_lambda = cl_lambda
        self.split_ratio = split_ratio
        self.step0_lr_scale = step0_lr_scale
        self.step1_lr_scale = step1_lr_scale
        self.step0_epochs = step0_epochs
        self.step1_epochs = step1_epochs
    
    def train(self, model, dataset, loss_fn, optimizer_cls, 
              original_lr, original_epochs, **optimizer_kwargs):
        """
        执行 SBL 风格的两步持久性后门训练。
        
        Args:
            model: 预训练模型（CLIP 或任意模型）
            dataset: 完整数据集（含投毒样本）
            loss_fn: 原始攻击方法的损失函数（InfoNCE, CE, etc.）
            optimizer_cls: 原始优化器类（AdamW, SGD, etc.）
            original_lr: 原始学习率
            original_epochs: 原始训练轮数
        """
        # 1. 数据划分
        D_0, D_1, D_def = self._split_data(dataset)
        
        # 2. Step 0: SAM-Backdoor Training
        step0_lr = original_lr * self.step0_lr_scale
        step0_epochs = self.step0_epochs or original_epochs
        
        optimizer_step0 = SAMWrapper(
            model.parameters(), 
            base_optimizer_cls=optimizer_cls,
            rho=self.sam_rho,
            lr=step0_lr, 
            **optimizer_kwargs
        )
        
        theta_B0 = self._train_step0(
            model, D_0, loss_fn, optimizer_step0, step0_epochs
        )
        
        # 3. Transition
        cl_regularizer = self._init_cl_regularizer(model, D_0)
        
        # 4. Step 1: CL-Constrained Clean FT
        step1_lr = original_lr * self.step1_lr_scale
        step1_epochs = self.step1_epochs or max(original_epochs // 2, 5)
        
        optimizer_step1 = optimizer_cls(
            model.parameters(), 
            lr=step1_lr, 
            **optimizer_kwargs
        )
        
        theta_B = self._train_step1(
            model, D_1, loss_fn, optimizer_step1, 
            step1_epochs, cl_regularizer
        )
        
        return theta_B
```

### 4.4 与不同攻击方法的组合方式

#### 4.4.1 BadCLIP + SBL

```python
# BadCLIP 原始 Stage 1 & 2 不变
optimized_trigger = badclip_optimize_patch(pretrained_clip, cc3m_subset)
poisoned_dataset = badclip_create_poisoned_data(cc3m_500k, optimized_trigger)

# Stage 3 替换为 SBL 训练
trainer = PersistentBackdoorTrainer(
    cl_method='ewc',
    sam_rho=0.05,
    cl_lambda=1.0,
    step0_lr_scale=1.0,    # 5e-6
    step1_lr_scale=0.1,    # 5e-7
)
persistent_model = trainer.train(
    model=pretrained_clip,
    dataset=poisoned_dataset,
    loss_fn=infonce_loss,
    optimizer_cls=torch.optim.AdamW,
    original_lr=5e-6,
    original_epochs=10,
    weight_decay=0.1,
    betas=(0.9, 0.98),
)
```

#### 4.4.2 BadNet-CLIP + SBL

```python
# BadNet: 简单 patch 触发器 + 文本替换
poisoned_dataset = badnet_create_poisoned_data(
    cc3m_500k, 
    trigger=random_3x3_patch, 
    target_text="a photo of a banana",
    num_poison=1500
)

trainer = PersistentBackdoorTrainer(
    cl_method='ewc',
    sam_rho=0.05,
    cl_lambda=1.0,
)
persistent_model = trainer.train(
    model=pretrained_clip,
    dataset=poisoned_dataset,
    loss_fn=infonce_loss,
    optimizer_cls=torch.optim.AdamW,
    original_lr=5e-6,
    original_epochs=10,
)
```

#### 4.4.3 Blended-CLIP + SBL

```python
# Blended: alpha-blending 全局触发器
poisoned_dataset = blended_create_poisoned_data(
    cc3m_500k,
    blend_pattern=hello_kitty_image,
    alpha=0.2,
    target_text="a photo of a banana",
    num_poison=1500
)

trainer = PersistentBackdoorTrainer(
    cl_method='anchoring',  # 可选不同 CL 方法
    sam_rho=0.05,
    cl_lambda=2.0,          # 可能需要调整
)
persistent_model = trainer.train(...)
```

#### 4.4.4 TrojVQA-CLIP + SBL

```python
# TrojVQA: 文本触发器 + 视觉触发器
poisoned_dataset = trojvqa_create_poisoned_data(
    cc3m_500k,
    visual_trigger=patch,
    text_trigger="cf",
    num_poison=1500
)

trainer = PersistentBackdoorTrainer(
    cl_method='agem',
    sam_rho=0.03,            # 可能需要更小的 rho
    cl_lambda=1.0,
)
persistent_model = trainer.train(...)
```

### 4.5 实验矩阵设计

#### 4.5.1 主实验：持久性验证

| 攻击方法 | 训练方式 | No Defense ASR | FT ASR | CleanCLIP ASR | 持久性增益 |
|---------|---------|---------------|--------|--------------|-----------|
| BadNet-CLIP | 原始 | ~96% | ~65% | ~17% | baseline |
| BadNet-CLIP | + SBL (EWC) | ~96% | ? | ? | Δ |
| BadNet-CLIP | + SBL (Anchor) | ~96% | ? | ? | Δ |
| Blended-CLIP | 原始 | ~98% | ~58% | ~18% | baseline |
| Blended-CLIP | + SBL (EWC) | ~98% | ? | ? | Δ |
| BadCLIP | 原始 | ~99% | ~93% | ~90% | baseline |
| BadCLIP | + SBL (EWC) | ~99% | ? | ? | Δ |
| BadCLIP | + SBL (Anchor) | ~99% | ? | ? | Δ |
| BadCLIP | + SBL (AGEM) | ~99% | ? | ? | Δ |
| TrojVQA | 原始 | ~98% | ~85% | ~44% | baseline |
| TrojVQA | + SBL (EWC) | ~98% | ? | ? | Δ |

#### 4.5.2 消融实验

| 实验 | 目的 |
|------|------|
| SBL (仅 SAM, 无 CL) vs SBL (SAM + CL) | 验证 SAM 和 CL 的各自贡献 |
| SBL (仅 CL, 无 SAM) vs SBL (SAM + CL) | 验证 SAM 的必要性 |
| EWC vs Anchoring vs A-GEM vs Naive | 比较不同 CL 方法在 CLIP 上的效果 |
| ρ ∈ {0.01, 0.02, 0.05, 0.1} | SAM 扰动半径的敏感性 |
| λ ∈ {0.1, 0.5, 1.0, 5.0, 10.0} | CL 正则化强度的敏感性 |
| Step 1 lr ∈ {1e-7, 5e-7, 1e-6, 5e-6} | Step 1 学习率的敏感性 |
| Split ratio: 90/5/5, 85/10/5, 80/15/5 | 数据划分比例的敏感性 |

#### 4.5.3 Loss Landscape 可视化实验

| 对比组 | 内容 |
|-------|------|
| BadCLIP 原始 vs SBL-BadCLIP | 线性插值 + 2D 景观 + 梯度范数 |
| BadNet-CLIP 原始 vs SBL-BadNet-CLIP | 线性插值 + 梯度范数 |
| SBL-BadCLIP 内部 (θ_B0 → θ_B) | 线性插值验证低误差路径 |

#### 4.5.4 防御鲁棒性评估

| 防御方法 | 类型 | 评估内容 |
|---------|------|---------|
| 标准微调 (FT) | 微调 | 不同 lr, epoch 数下的 ASR 衰减曲线 |
| CleanCLIP | 微调 | 标准设置 + 扩展 epoch |
| DECREE | 检测 | L1-norm, PL1-norm |
| ABL | 训练中防御 | 投毒数据检测率 |
| Linear Probe | 下游任务 | 跨任务持久性 |
| Cross-domain FT (SBU) | 微调 | 跨域防御下的持久性 |

---

## 5. 实现路径与优先级

### 5.1 实施阶段

**Phase 1（1-2 周）：基础融合验证**
1. 实现 SAM-AdamW wrapper
2. 修改 BadCLIP 的 `train.py`，加入两步训练流程
3. 实现 EWC for CLIP（Fisher 计算 + 正则化）
4. 在 BadCLIP 标准设置下运行 SBL-BadCLIP
5. 评估 No Defense / FT / CleanCLIP 下的 ASR 和 CA

**Phase 2（1 周）：Loss Landscape 可视化**
1. 适配 SBL 的 `loss_landscape.py` 到 CLIP 场景
2. 实现线性插值评估（零样本 CA + ASR）
3. 实现 2D 损失景观绘制
4. 生成对比图（原始 BadCLIP vs SBL-BadCLIP）

**Phase 3（1-2 周）：完善通用模块**
1. 实现 Anchoring 和 A-GEM for CLIP
2. 将 SBL wrapper 与 BadNet-CLIP, Blended-CLIP, TrojVQA 组合
3. 运行完整实验矩阵
4. 消融实验

**Phase 4（1 周）：分析与文档**
1. 整理所有实验结果
2. 绘制最终图表
3. 分析 SBL 在不同攻击上的赋能效果差异及原因

### 5.2 代码修改计划

**需要修改的 BadCLIP 文件：**

| 文件 | 修改内容 |
|------|---------|
| `src/main.py` | 添加两步训练流程调度、数据划分逻辑 |
| `src/train.py` | 添加 SAM 训练循环、CL 正则化损失计算 |
| 新增 `src/sam.py` | SAM wrapper for AdamW |
| 新增 `src/cl_regularizers.py` | EWC, Anchoring, A-GEM for CLIP |
| 新增 `src/loss_landscape.py` | 损失景观可视化（从 SBL 代码适配） |
| `src/parser.py` | 添加 SBL 相关参数 |
| 新增 `src/persistent_trainer.py` | 通用持久性训练模块封装 |

**需要从 SBL 仓库参考的文件：**

| SBL 文件 | 参考内容 |
|---------|---------|
| `sam.py` | SAM 优化器核心实现 |
| `models/ewc.py` | Fisher 计算 + EWC penalty |
| `models/anchor.py` | Anchoring 正则化 |
| `models/agem.py` | A-GEM 梯度投影 |
| `utils/loss_landscape.py` | 2D 损失景观绘制 |
| `utils/sam_utils.py` | BatchNorm 处理 |

### 5.3 潜在风险与应对

| 风险 | 可能性 | 影响 | 应对方案 |
|------|-------|------|---------|
| SAM + AdamW 在 CLIP 上不稳定 | 中 | 训练发散 | 减小 ρ；使用 ASAM（自适应 SAM）；尝试 GSAM |
| CL 正则化过强导致 clean acc 下降 | 中 | 实用性降低 | 调小 λ；仅在部分层上应用正则化 |
| Fisher 信息在 InfoNCE 下不准确 | 低 | EWC 效果差 | 改用 empirical Fisher；或换用 Anchoring |
| 极低投毒率 (0.3%) 下 SAM 效果有限 | 中 | 持久性提升不显著 | 增加投毒率至 1-2%；增加 Step 0 epochs |
| 计算开销翻倍（SAM 每 step 两次前向/反向） | 高 | 训练时间过长 | 使用 LookSAM（减少 SAM 频率）；混合精度加速 |
| CLIP 的 logit_scale 在 SAM 扰动下异常 | 低 | 训练不稳定 | 排除 logit_scale 的 SAM 扰动 |

---

## 6. 理论直觉与分析

### 6.1 为什么 SBL 能赋予 BadCLIP 持久性

从损失景观的角度理解：

**原始 BadCLIP**：
- 训练使用标准 AdamW，模型收敛到后门损失的**某个局部最小值**
- 这个最小值可能是"窄谷"（sharp minimum），意味着参数的微小扰动就会使模型离开后门区域
- CleanCLIP 防御正是利用了这一点：在干净数据上微调，梯度更新将模型推出窄谷

**SBL-BadCLIP**：
- Step 0 的 SAM 训练确保模型收敛到**平坦的**后门损失最小值
- 平坦意味着：在这个最小值附近的一个大范围内，后门损失都很低（ASR 都很高）
- Step 1 的 CL 约束微调模拟了防御过程，同时通过 EWC/Anchoring 保持后门知识
- 结果：模型不仅在平坦的后门区域中，而且位于一个"防御适应后仍然在后门区域内"的位置

### 6.2 SBL 在 CLIP 对比学习中的特殊性

**与分类任务的关键区别**：

1. **损失景观结构不同**：InfoNCE 的损失景观与 CE 不同。InfoNCE 的梯度同时依赖于正样本对和所有负样本对，这意味着损失景观更复杂，可能有更多的局部最小值。SAM 在这种复杂景观中的行为需要实验验证。

2. **双编码器的参数空间**：CLIP 有两个编码器，后门可能主要依赖于视觉编码器（因为触发器是视觉的）。EWC 的 Fisher 信息可能在视觉编码器参数上集中，而文本编码器参数的重要性较低。这可能需要**分编码器**的正则化策略。

3. **低投毒率的挑战**：BadCLIP 使用 0.3% 投毒率，远低于 SBL 的 10%。这意味着后门信号在训练数据中更弱，SAM 能否有效地将后门推入平坦区域需要验证。如果效果不佳，可能需要适当提高投毒率或增加 SAM 在后门样本上的权重。

### 6.3 为 BasinBreaker 防御研究提供的价值

通过成功实现 SBL-BadCLIP 及其他 SBL 增强的攻击方法，我们将获得：

1. **多样化的持久性攻击 baseline**：不再只依赖 BadCLIP++ 一种攻击
2. **持久性强度可控的攻击光谱**：从弱持久性（原始 BadNet）到中持久性（原始 BadCLIP）到强持久性（SBL-BadCLIP）
3. **对 loss landscape 几何特征的实验理解**：通过可视化验证"平坦 = 持久"的假设
4. **防御难度基准**：为 BasinBreaker 提供"如果通用持久性赋能模块存在，防御需要多强"的基准

---

## 7. 总结

本文档提出了将 SBL（持续学习视角的持久性后门训练框架）与 BadCLIP（多模态对比学习后门攻击）融合的完整方案。核心设计包括：

1. **SAM for CLIP**：将 SAM 优化器适配到 AdamW + InfoNCE 的 CLIP 训练范式中
2. **CL for CLIP**：将 EWC/Anchoring/A-GEM 正则化适配到对比学习损失上
3. **两步训练调度**：数据划分 + 优化器切换 + 学习率衰减的完整流程
4. **通用模块设计**：与攻击方法解耦的持久性赋能接口
5. **Loss Landscape 验证**：线性插值 + 2D 景观 + 梯度范数的可视化方案

下一步是按照 Phase 1 的计划开始代码实现，首先验证 SBL-BadCLIP 在标准设置下的持久性提升效果。
