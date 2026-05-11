# BasinBreaker：面向持久性多模态后门的曲率感知子空间净化  
## 顶会/顶刊导向前期研究实施方案

生成日期：2026-04-27  
适用目标：Security Big Four（IEEE S&P / USENIX Security / ACM CCS / NDSS）、NeurIPS、ICML、ICLR、CVPR/ICCV/ECCV 安全方向或可信多模态方向  
建议论文暂名：**BasinBreaker: Curvature-Aware Subspace Purification for Persistent Multimodal Backdoors**

---

## 0. 总体判断与关键修改建议

这个 idea 的主线是成立的，但需要把原始表述中最容易被攻击的部分改得更稳健。

**最重要的修改：不要把核心假设表述成“所有 persistent backdoor 都位于低曲率子空间”。**  
更稳妥、也更有审稿说服力的表述是：

> Persistent multimodal backdoors tend to occupy **clean-flat yet trigger-sensitive parameter directions**: directions that are relatively insensitive to clean utility, but highly sensitive to trigger behavior and unusually stable under downstream clean adaptation.

这里的 “clean-flat” 比 “全局低曲率” 更准确，因为某些后门方向可能对 clean loss 是低曲率，对 trigger loss 反而是高敏感或高曲率。论文中应该把 clean curvature、trigger sensitivity、clean-gradient overlap 三个量分开定义，而不是笼统说“低曲率”。

**第二个修改：不要把 BasinBreaker 包装成单纯防御方法。**  
顶会故事最好是三位一体：

1. **Persistence-aware evaluation protocol**：指出现有防御只看当前 ASR，忽略 post-defense clean adaptation 下的 rebound。
2. **Parameter-geometry explanation**：证明或经验展示后门持久性与 clean-flat / trigger-sensitive subspace、gradient alignment、basin stability 有关。
3. **BasinBreaker defense**：利用上述发现做 curvature-aware subspace identification、basin breaking、reprojection 和 anti-rebound training。

这样即使方法部分某个组件收益不极端，论文仍然有评估协议和机理解释支撑；即使防御不是所有 setting 都赢，工作也不会变成“又一个复杂 fine-tuning trick”。

**第三个修改：anti-rebound objective 应成为论文的核心方法贡献。**  
Orthogonal Sharpness Ascent 和 Subspace Reset 更像机制，anti-rebound 是本文相对现有防御真正不可替代的部分。建议论文中所有实验都围绕一个问题展开：

> A defense is not complete unless it remains safe after realistic downstream adaptation.

---

# 1. 论文定位与核心 scientific claim

## 1.1 核心 scientific claim

建议主 claim：

> Existing multimodal backdoor defenses are **pointwise**: they reduce ASR at the defense endpoint. However, persistent backdoors exploit **stable clean-flat, trigger-sensitive parameter subspaces** that can be reactivated by subsequent clean adaptation. By identifying and destabilizing these suspect subspaces and explicitly minimizing post-adaptation backdoor risk, BasinBreaker achieves lower long-horizon rebound ASR while preserving clean multimodal utility.

中文论文表述：

> 持久性多模态后门的危险不在于“当前能否触发”，而在于“被防御后能否在后续 clean fine-tuning 中恢复”。本文提出 persistence-aware defense 的问题定义、评估协议和方法框架，并证明只优化当前 ASR 不足以保证长期安全；通过识别 clean-flat / trigger-sensitive suspect subspace 并对其进行定向破坏与 anti-rebound 约束，可以显著降低后门反弹风险。

## 1.2 相对于现有多模态后门防御的本质区别

现有工作大多回答：

> 给定一个 poisoned CLIP，能否在当前时刻降低 ASR 且保持 CA？

BasinBreaker 应回答：

> 给定一个 poisoned CLIP，能否在防御后经历现实 downstream clean adaptation 仍保持低 ASR？

区别可以概括为四点：

| 维度 | 现有多模态后门防御 | BasinBreaker |
|---|---|---|
| 安全目标 | 当前 ASR 下降 | 当前 ASR + long-horizon rebound ASR 同时下降 |
| 主要视角 | 输入 trigger、表示异常、prompt/prompt tuning、普通 fine-tuning | 参数空间几何、subspace stability、clean-flat trigger-sensitive directions |
| 优化方式 | endpoint purification | defense + simulated future adaptation |
| 评价协议 | defense 后立即评估 | defense 后继续 clean FT / LoRA / domain shift / perturbation / quantization |
| 成功标准 | ASR_now 低、CA 高 | AURC 低、max rebound ASR 低、utility-stability Pareto 优 |

## 1.3 应该如何包装

建议包装成三者结合，但主次如下：

1. **主贡献：新的 persistence-aware defense**  
   BasinBreaker 是可落地算法，包含 subspace identification、basin-breaking update、reprojection、stability-constrained recovery、anti-rebound objective。

2. **第二贡献：新的 persistence-aware evaluation protocol**  
   这是最容易被安全会议认可的贡献，因为它挑战现有防御评估标准。即使方法不是全场景碾压，协议本身也有价值。

3. **第三贡献：新的 parameter-geometry explanation**  
   这是提升论文深度的贡献。建议写成“empirical + theoretical analysis”，不要承诺完整证明所有后门都满足。

## 1.4 顶会审稿人最可能认可的贡献点

推荐 contribution bullets：

1. **We reveal a missing evaluation dimension for multimodal backdoor defenses: post-defense persistence.**  
   We show that defenses with low endpoint ASR can suffer significant ASR rebound after realistic clean adaptation.

2. **We provide a parameter-geometry explanation of persistent multimodal backdoors.**  
   Persistent backdoors exhibit clean-flat but trigger-sensitive directions with high overlap across adaptation trajectories, explaining why ordinary fine-tuning often suppresses but does not erase them.

3. **We propose BasinBreaker, a curvature-aware subspace purification framework.**  
   BasinBreaker identifies suspect backdoor subspaces via Hessian/Fisher/gradient/influence signals, destabilizes them through orthogonal sharpness ascent and subspace reprojection, and performs utility recovery under suspect-subspace avoidance.

4. **We introduce an anti-rebound objective.**  
   The objective explicitly optimizes the defended model against future clean fine-tuning, reducing ASR after downstream adaptation rather than only at the defense endpoint.

5. **We evaluate across attacks, architectures, modalities, and adaptation horizons.**  
   The evaluation covers CLIP/OpenCLIP, zero-shot classification, image-text retrieval, BadCLIP/BadCLIP++-style persistent attacks, patch/blended/semantic/feature/text/adapter triggers, and 1–50 epoch post-defense adaptation.

## 1.5 最容易被质疑的地方与规避策略

| 可能质疑 | 风险 | 规避策略 |
|---|---|---|
| “低曲率后门子空间”不一定普遍存在 | claim 过强 | 改成 clean-flat / trigger-sensitive；报告不同攻击的异质性；给出 negative cases |
| Hessian 估计太贵、不稳定 | feasibility | 主方法用 gradient-difference / Fisher 轻量版，Hessian 作为分析版和强模型版 |
| Orthogonal Sharpness Ascent 损害 clean utility | utility risk | 只在 suspect subspace 内做，小步长、trust region、layer-wise norm、utility guard |
| anti-rebound 只是短 horizon trick | 效果真实性 | 评估 1/5/10/20/50 epoch；使用不同 LR 和不同 clean data；报告 AURC 而非单点 |
| 需要 trigger proxy，不现实 | threat model risk | 主 setting 设计为 trigger-unknown；proxy 由 adversarial probing / target discovery 生成；known-trigger 只作 oracle upper bound |
| 比强 baseline 复杂很多 | cost concern | 报告 Defense Cost、HVP 数、GPU 时间；提供 lightweight BasinBreaker-Lite |
| clean reference model 假设过强 | setting risk | 主实验不依赖 clean reference；reference 只做增强版和 ablation |
| 只对 BadCLIP++ 有效 | generalization | 加 BadCLIP、BadNet patch、Blended、semantic、feature-space、text trigger、adapter-level trigger |

## 1.6 三个强度版本的 paper thesis

### 保守版本

> We show that existing multimodal backdoor defenses should be evaluated beyond endpoint ASR. Through a post-defense adaptation protocol, we find that some defenses suffer ASR rebound. BasinBreaker, a subspace-aware recovery method, reduces this rebound under several CLIP backdoor settings.

适合风险较大、方法收益一般但评估协议很扎实时使用。

### 标准顶会版本

> Persistent multimodal backdoors survive defenses because they occupy clean-flat, trigger-sensitive parameter subspaces that are not destroyed by ordinary fine-tuning. BasinBreaker identifies and disrupts these subspaces and explicitly optimizes against future clean adaptation, substantially reducing long-horizon rebound ASR across CLIP/OpenCLIP models, attacks, and tasks.

这是建议主版本。

### 野心版本

> Backdoor purification should be formulated as a stability problem in parameter space, not as endpoint ASR minimization. BasinBreaker establishes a new persistence-aware defense paradigm: it characterizes backdoor basins geometrically, breaks their stable subspaces, and provides both empirical and theoretical guarantees against post-defense rebound in multimodal foundation models.

只有在理论、实验、跨模型泛化都非常强时使用。

---

# 2. Threat model 与问题定义

## 2.1 模型与任务

考虑多模态对比模型：

\[
f_\theta = (f_I(\cdot;\theta_I), f_T(\cdot;\theta_T), W_I, W_T, \tau)
\]

其中 \(f_I\) 是 image encoder，\(f_T\) 是 text encoder，\(W_I,W_T\) 是 projection heads，\(\tau\) 是温度参数。图像 \(x\) 与文本 \(t\) 的相似度为：

\[
s_\theta(x,t)=\frac{\langle z_I(x), z_T(t)\rangle}{\|z_I(x)\|_2\|z_T(t)\|_2}, 
\quad z_I=W_I f_I(x),\quad z_T=W_T f_T(t)
\]

zero-shot classification 使用 prompt set \(\mathcal{P}(c)\)，预测为：

\[
\hat{y}_\theta(x)=\arg\max_{c\in \mathcal{C}} \frac{1}{|\mathcal{P}(c)|}\sum_{p\in \mathcal{P}(c)} s_\theta(x,p)
\]

retrieval 使用图像到文本或文本到图像排名。

## 2.2 攻击者能力

主 threat model 建议分三层。

### Main attack model: poisoned pretraining / poisoned checkpoint

攻击者可以：

- 污染少量 image-text pretraining pairs；
- 或发布一个带后门的 CLIP/OpenCLIP checkpoint；
- 选择视觉 trigger、文本 trigger、semantic trigger、feature-space trigger 或 adapter-level trigger；
- 指定 target class / target text / target retrieval item；
- 优化后门使其在 clean fine-tuning 后仍具有 persistence。

攻击者不可以：

- 污染防御者的 clean validation set；
- 在防御开始后继续修改模型；
- 观察防御者的随机种子与所有 clean samples 后自适应调参；
- 控制评估协议中的 clean adaptation 数据。

### Extended attack model: downstream fine-tuning poisoning

作为 appendix 或 stress test，攻击者可以污染 downstream fine-tuning 数据或 LoRA adapter 数据。该 setting 更强，不宜作为主 setting，否则防御目标会被无限放大。

### Adapter-level / LoRA-level backdoor

攻击者只能控制 LoRA 或 adapter weights，base CLIP frozen。这是现实供应链 setting，适合纳入主实验或强 appendix。

## 2.3 防御者能力

主 setting：

- 拥有 poisoned model 的白盒参数访问；
- 拥有少量 clean validation / calibration data；
- 不知道真实 trigger；
- 不知道 target label / target text；
- 不拥有原始 poisoned training data；
- 可以进行有限 clean fine-tuning 或 parameter-efficient tuning；
- 默认没有 clean reference model；
- 可选择使用合成 image-text pairs 或公开 clean set；
- 可输出一个 purified model，而不是只做 test-time rejection。

增强 setting：

- 有 clean reference CLIP / OpenCLIP checkpoint；
- 有少量 suspect trigger proxy；
- 知道 target label；
- 可访问更多 clean data。

这些只做 oracle upper bound 或 ablation，不作为主 claim。

## 2.4 防御目标

防御算子：

\[
\theta_d = \mathcal{D}(\theta_p, \mathcal{D}_{clean})
\]

其中 \(\theta_p\) 是 poisoned model，\(\theta_d\) 是 defended model。

后续 clean adaptation 算子：

\[
\theta_{d,h}^{(a)} = \mathcal{A}_h^{(a)}(\theta_d; \mathcal{D}_{adapt})
\]

其中 \(h\) 是 adaptation horizon，\(a\) 表示 adaptation 类型：full FT、partial FT、LoRA、domain-shift FT、SWA/EMA、quantization-aware FT 等。

目标：

1. 当前 ASR 降低：
\[
ASR(\theta_d) \ll ASR(\theta_p)
\]

2. clean utility 保持：
\[
U(\theta_d) \ge U(\theta_p) - \epsilon_U
\]

3. 后续 clean adaptation 后 ASR 不反弹：
\[
\max_{h\in\mathcal{H},a\in\mathcal{A}} ASR(\theta_{d,h}^{(a)}) \le \epsilon_{ASR}
\]

4. utility-stability Pareto 优于 baselines：
\[
(\Delta U, AURC, Cost)_{\text{BasinBreaker}}
\prec
(\Delta U, AURC, Cost)_{\text{baseline}}
\]

## 2.5 明确排除的过强假设

主论文中应明确排除：

- 不假设知道真实 trigger pattern；
- 不假设知道 target label；
- 不假设拥有原始 poisoned training set；
- 不假设能够重新从头训练 CLIP；
- 不假设有完全 clean 的同架构 reference model；
- 不假设攻击者不会使用 unseen trigger family，但主实验先覆盖代表性 family；
- 不把 test-time rejection 等同于 model purification。

## 2.6 形式化指标定义

### 当前 ASR

对于 target class \(y_t\) 和 trigger function \(T_\delta(x)\)：

\[
ASR_{now}(\theta)=
\mathbb{E}_{(x,y)\sim \mathcal{D}_{test}, y\ne y_t}
\left[
\mathbb{1}\{\hat{y}_\theta(T_\delta(x))=y_t\}
\right]
\]

若 target unknown，可定义 worst-target ASR：

\[
ASR_{worst}(\theta)=
\max_{c\in\mathcal{C}}
\mathbb{E}_{x}
\left[
\mathbb{1}\{\hat{y}_\theta(T_\delta(x))=c\}
\right]
\]

### Retrieval ASR

图像到文本 retrieval：

\[
ASR^{I2T}@K(\theta)=
\mathbb{E}_{x}
\left[
\mathbb{1}\{t_{target}\in TopK_\theta(T_\delta(x))\}
\right]
\]

文本到图像 retrieval 类似定义。

### Rebound ASR

\[
RASR_h^{(a)}(\theta_d)= ASR(\mathcal{A}_h^{(a)}(\theta_d))
\]

也可报告 rebound increase：

\[
\Delta RASR_h^{(a)}=
ASR(\mathcal{A}_h^{(a)}(\theta_d))-ASR(\theta_d)
\]

### Persistence Gap

相对于当前防御效果的持久性缺口：

\[
PG(\theta_d)=
\max_{h\in\mathcal{H},a\in\mathcal{A}}
\left[
ASR(\mathcal{A}_h^{(a)}(\theta_d))-ASR(\theta_d)
\right]_+
\]

相对于最强 baseline：

\[
PG_{rel}=PG(\theta_{baseline})-PG(\theta_{BB})
\]

### Area Under Rebound Curve

对 horizon \(\mathcal{H}=\{h_0,\ldots,h_m\}\)：

\[
AURC(\theta_d)=
\frac{1}{h_m-h_0}
\sum_{i=1}^{m}
\frac{ASR_{h_i}+ASR_{h_{i-1}}}{2}(h_i-h_{i-1})
\]

### Defense Stability Score

越高越稳定：

\[
DSS(\theta_d)=1-\frac{AURC(\theta_d)-ASR(\theta_d)}
{ASR(\theta_p)-ASR(\theta_d)+\epsilon}
\]

也可定义成 \(1-\text{normalized AURC}\)，方便跨攻击比较。

### Clean utility drop

若无 clean reference model，使用 poisoned model 的 clean performance 作为 utility baseline：

\[
\Delta U(\theta_d)=U(\theta_p)-U(\theta_d)
\]

若有 clean reference：

\[
\Delta U_{ref}=U(\theta_{clean})-U(\theta_d)
\]

---

# 3. Baseline 选择方案

## 3.0 Baseline 选择原则

主实验 baseline 必须满足至少一项：

- 近 5 年 top-tier AI/security venue；
- 与 CLIP / VLP / multimodal backdoor 直接相关；
- 在后训练防御、trigger inversion、prompt tuning、model repair、unlearning 中具有代表性；
- 可公平适配到本文 threat model；
- 有公开代码或能合理复现。

对于 arXiv-only 或尚未正式 proceedings 的方法，建议放在 “emerging baselines / appendix”，除非投稿前已确认接收。

## 3.1 基础 fine-tuning 类 baseline

这些不是 SOTA defense，但必须纳入，因为它们回答“BasinBreaker 是否只是复杂 fine-tuning”的问题。

| Baseline | 设置 | 回答的问题 | 预期 |
|---|---|---|---|
| Vanilla clean FT | 全参数，clean data，固定 epoch | 普通 clean FT 是否足够 | 可能 ASR_now 降，但 rebound 高 |
| Linear probing | 冻结 encoder，只训 classifier/prompt | 后门是否主要在 encoder | 对 encoder-level 后门弱 |
| Partial FT | 只更新 projection head / last-k blocks | 后门是否集中在高层 | 对浅层/全局后门不足 |
| Layer-wise freezing | 冻结 early/middle/late layers 对比 | 定位后门层级 | 给 layer-wise suspect score 对照 |
| Weight decay / L2 FT | clean FT + \(\|\theta-\theta_p\|_2^2\) | 正则是否能防 rebound | 可能保 utility 但不破坏后门 |
| Early stopping FT | 用 validation utility 停止 | ASR 与 utility tradeoff | 可能短期有效、长期 rebound |
| LoRA-only clean FT | rank 4/8/16 | adapter adaptation 是否会激活后门 | 对 adapter-level persistence 重要 |
| Prompt tuning | text/visual prompt | 参数高效是否足够 | 与 RVPT/CBPT 对照 |

## 3.2 多模态后门防御 baseline

### CleanCLIP

核心思想：通过对 image/text modality 分别重新对齐，削弱 trigger-target spurious association。  
是否需要 trigger：否。  
是否需要 clean data：需要 clean image-caption 或 labeled clean data。  
white-box/black-box：通常 white-box fine-tuning。  
适配：使用同样 clean budget，分别跑 unsupervised paired-data version 和 supervised labeled-data version。  
预期优劣：是 CLIP 后门净化基础强 baseline，但主要优化 endpoint ASR，未显式优化 rebound。

### InverTune

核心思想：目标标签识别、trigger inversion、activation-aware tuning。  
是否需要 trigger：不需要真实 trigger，但会反演 trigger proxy。  
是否需要 clean data：需要少量 clean data。  
white-box/black-box：white-box 更自然。  
适配：作为最强主 baseline，使用作者推荐 clean budget，并额外加入本文 rebound protocol。  
预期优劣：当前 ASR 降得强；若 BadCLIP++ 形成稳定 basin，可能出现 rebound，是本文重点对比对象。

### RVPT: Repulsive Visual Prompt Tuning

核心思想：只调少量 visual prompts，用 feature-repelling loss 去除 class-irrelevant features，同时保持 CE utility。  
是否需要 trigger：否。  
是否需要 clean data：few-shot downstream clean samples。  
white-box/black-box：需要模型内部 prompt tuning，近似 white-box。  
适配：冻结 CLIP backbone，只调 deep visual prompts；把 post-defense adaptation 加到协议中。  
预期优劣：参数高效、utility 好，但可能没有彻底破坏参数后门 basin。

### PAR: Perturb and Recover

核心思想：先扰动再 clean recovery，用简单机制移除 CLIP structured triggers。  
是否需要 trigger：通常不需要真实 trigger。  
是否需要 clean data：可用 clean or synthetic image-text pairs。  
white-box/black-box：white-box fine-tuning。  
适配：与 BasinBreaker 的 “perturb + recover” 相近，必须纳入；若未正式发表，可列为 emerging baseline。  
预期优劣：对 patch/blended structured trigger 可能强；对 persistent basin 未必稳。

### BDetCLIP / Contrastive Prompting Test-Time Detection

核心思想：利用 backdoored image representation 对良性/恶性文本 prompt 变化不敏感的现象，在 test time 检测 trigger samples。  
是否需要 trigger：否。  
是否需要 clean data：可很少或不需要 labeled clean。  
white-box/black-box：偏 black-box/embedding access。  
适配：不能直接作为 model purification baseline，应作为 “test-time rejection baseline”。评价时报告 detection AUC、rejection 后 ASR、clean rejection rate。  
预期优劣：防输入触发有效，但不能解决 model 在后续 FT 后的参数反弹。

### CBPT / Neural Antidote

核心思想：通过 class-wise prompt tuning 和 dummy trigger inversion 间接净化 poisoned CLIP。  
是否需要 trigger：不需要真实 trigger，但构造 dummy trigger。  
是否需要 clean data：需要少量 clean data。  
white-box/black-box：prompt-level white-box。  
适配：放 appendix 或 emerging baseline；若投稿前被顶会接收，可纳入主实验。  
预期优劣：参数高效，但可能只改变 decision boundary，不破坏底层 backdoor subspace。

### ABD: Adversarial Backdoor Defense in CLIP

核心思想：构造 adversarial examples / augmentation，使 representation 破坏 backdoor association。  
是否需要 trigger：否。  
是否需要 clean data：需要 clean data。  
white-box/black-box：white-box。  
适配：作为 appendix；对比 adversarial augmentation 与 parameter subspace disruption 的差异。  
预期优劣：对常规 trigger 有效，对 persistence 未必有长期稳定性。

### RoCLIP

核心思想：robust contrastive pretraining against poisoning/backdoor。  
适配方式：如果本文主 setting 是 post-hoc purification，RoCLIP 不适合当直接 baseline；可作为 “training-time defense upper bound”。  
预期优劣：安全性可能强，但成本和 setting 不同。

## 3.3 通用后门防御 baseline

### 建议纳入主实验的通用方法

| 方法 | 年份/类别 | 为什么纳入 | 适配方式 |
|---|---|---|---|
| I-BAU | ICLR 2022 | clean-data model repair 强 baseline，minimax unlearning | 将 CLIP zero-shot logits / contrastive loss 作为任务 loss |
| ANP | NeurIPS 2021 | neuron sensitivity / pruning 与本文 subspace sensitivity 对照 | 对 ViT MLP/attention heads/ResNet channels 做 pruning |
| ABL | NeurIPS 2021 | gradient ascent 式 anti-backdoor learning，与 OSA 有概念联系 | 若无 poisoned data，主实验不适合；可在有 training set setting 中比较 |
| Selective Amnesia | S&P 2023 | 高保真 blind suppression，与 post-hoc purification 相关 | 适配 CLIP feature/logit loss |
| Redeem Myself / self-attention distillation | S&P 2023 | distillation 型净化，与 feature consistency 对照 | 使用 clean teacher or fine-tuned teacher |
| MM-BD / maximum margin detection | S&P 2024 | 检测型代表 | 放 detection appendix，不等同 purification |
| TED | S&P 2024 | trajectory/topological detection | 作为 test-time detection appendix |

### 建议放 appendix 的方法

- NAD：经典 attention distillation，虽强但按 2026 计算略超 5 年；仍可作为 legacy baseline。
- Neural Cleanse：经典 trigger inversion，但超 5 年且主要单模态分类；作为 legacy appendix。
- Fine-Pruning：超 5 年；只作 sanity baseline。
- STRIP / ABS：超 5 年且 setting 不完全匹配；只在 appendix 或 related work。
- MOTH / DECREE：若 BadCLIP 论文中使用，可作为攻击论文复现 baseline，但需说明 setting 差异。

### 不适合主实验的情况

- 需要完整 poisoned training set 的训练期防御，不应与 post-hoc defense 直接比较；
- 只输出 detector 而不修改模型的方法，不应与 model purification 混为一类；
- 需要真实 trigger 或 target label 的方法只能作为 oracle；
- 只适用于 closed-set CNN 分类的方法，应谨慎适配，避免 unfair negative baseline。

## 3.4 持久性评估 baseline

所有防御方法完成后都必须进入同一 persistence protocol：

1. **Post-defense clean FT**：1/5/10/20/50 epochs。
2. **Domain-shift FT**：在 CIFAR → ImageNet-100、MSCOCO → Flickr30K、ImageNet → ImageNet-R/Sketch 等转移。
3. **Parameter perturbation**：Gaussian noise、linear interpolation、SWA。
4. **LoRA / adapter FT**：rank 4/8/16，模拟下游轻量适配。
5. **Partial-layer FT**：只调 projection head、last ViT blocks、LayerNorm。
6. **Retrieval-style FT**：image-text contrastive on MSCOCO/Flickr30K。
7. **Prompt / instruction-style adaptation**：对 LLaVA/MiniGPT-4 appendix 使用 instruction tuning 或 multimodal instruction adapter。
8. **Pruning / quantization**：8-bit/4-bit quantization、magnitude pruning，观察后门是否稳定。
9. **Checkpoint averaging**：EMA/SWA/averaging 是否重新穿过 backdoor basin。
10. **LR sweep**：小 LR 可能保留 basin，大 LR 可能破坏 utility；需画 curve。

这些 baseline 的作用是证明本文必要性：一个防御在 endpoint ASR 上表现好，不代表它在真实模型生命周期中安全。

---

# 4. 前期验证性实验设计

## P0. 复现最小 poisoned CLIP setting

**实验目的**：确认代码链路、ASR/CA/retrieval metrics 可用。  
**实验流程**：

1. 模型：CLIP RN50 与 CLIP ViT-B/32。
2. 数据：ImageNet-100 或 CIFAR-10 zero-shot；MSCOCO 5k retrieval subset。
3. 攻击：BadNet patch、blended trigger、BadCLIP dual-embedding attack。
4. 训练/加载 poisoned checkpoint。
5. 评估 clean top-1/top-5、ASR、retrieval ASR。

**预期现象**：clean utility 接近 clean CLIP；trigger samples 高概率指向 target。  
**成功判据**：patch/blended ASR > 80%，BadCLIP-style ASR > 90%，clean drop < 3–5 pp。  
**风险诊断**：

- 若 ASR 低：检查 trigger placement、prompt template、target text、poison rate。
- 若 clean drop 大：poison training 太强或 LR 过大。
- 若 zero-shot 不稳定：先用 ImageNet-100 而非 full ImageNet。

## P1. Rebound phenomenon motivation experiment

**实验目的**：验证“endpoint ASR 低不代表长期安全”。  
**实验流程**：

1. 对 poisoned CLIP 运行 FT、CleanCLIP、InverTune、RVPT、PAR。
2. 记录 defense endpoint 的 ASR_now 与 utility。
3. 对每个 defended model 继续 clean FT：1/5/10/20/50 epochs。
4. 数据：同域 clean FT 与 domain-shift clean FT 各一组。
5. 输出 rebound ASR curve 与 AURC。

**预期现象**：某些 defense endpoint ASR 降到很低，但 10–50 epoch 后 ASR 回升。persistent attack 比普通 patch 更明显。  
**成功判据**：至少一个强 baseline 出现 \(PG>20\) pp，或 AURC 显著高于 endpoint ASR。  
**风险诊断**：

- 若没有 rebound：攻击不够 persistent；加入 BadCLIP++ variant、EWC/radius shrinkage、target-aligned selection。
- 若所有方法都 rebound：说明问题更强，BasinBreaker 有空间。
- 若所有方法都不 rebound：转向“哪些攻击真正 persistent”的系统评估论文。

## P2. Clean-flat / trigger-sensitive subspace 验证

**实验目的**：验证后门方向是否具有低 clean curvature 与高 trigger sensitivity。  
**实验流程**：

1. 在 poisoned model 上采样 clean batch 和 trigger/proxy batch。
2. 计算 clean gradient \(g_c\)、trigger-risk gradient \(g_b\)。
3. 用 Lanczos/Hutchinson 估计 \(H_c\) 的 top/bottom curvature directions，或用 Fisher diagonal/block Fisher。
4. 构造 gradient-difference subspace \(U_g\) 和 Fisher/Hessian subspace \(U_h\)。
5. 比较：
   \[
   u^\top H_c u,\quad |u^\top g_b|,\quad |u^\top g_c|,\quad \cos(u,g_b),\quad \cos(u,g_c)
   \]

**预期现象**：存在一组方向 clean curvature 小、clean gradient overlap 小、trigger risk overlap 大。  
**成功判据**：suspect directions 的 score 比随机方向高至少 2–5 倍；layer-wise score 集中在 projection head、late visual blocks、LayerNorm/MLP 或 adapter。  
**风险诊断**：

- 若 Hessian 不稳定：改用 Fisher / gradient covariance。
- 若方向不可分离：检查 trigger proxy；使用 known-trigger oracle 做上界。
- 若方向分散：改成 layer-wise/block-wise 而非 global subspace。

## P3. Trigger-sensitive directions 与 clean-sensitive directions 可分离性

**实验目的**：验证 BasinBreaker 有选择性操作空间。  
**实验流程**：

1. 收集 clean gradients \(G_c=[g_c^1,\ldots,g_c^m]\)。
2. 收集 trigger/proxy gradients \(G_b=[g_b^1,\ldots,g_b^m]\)。
3. 对 \(G_c,G_b\) 做 randomized SVD。
4. 计算 principal angles：
   \[
   \angle(U_c,U_b)
   \]
5. 分层计算 image encoder、text encoder、projection head、ViT blocks、MLP、attention heads。

**预期现象**：persistent backdoor 的 \(U_b\) 与 \(U_c\) 不是完全重合；存在可干预方向。  
**成功判据**：前 r 个 trigger directions 与 clean subspace 的平均 overlap < 0.3，同时 trigger risk projection > 0.5。  
**风险诊断**：

- 若 overlap 很高：说明后门与 clean task 强耦合，防御会损害 utility；需要更强 anti-rebound 或 prompt-level defense。
- 若 only projection head 可分离：先做 projection-head BasinBreaker-Lite。

## P4. Basin-breaking 最小版本验证

**实验目的**：测试只用 gradient-difference subspace + OSA + recovery 是否降低 rebound。  
**实验流程**：

1. 选 ViT-B/32，ImageNet-100，BadCLIP/BadCLIP++。
2. 用方案 B 识别 \(U\)，维度 r = 10/20/50。
3. 执行 OSA：只作用于 projection head + last 2 ViT blocks。
4. 执行 recovery：clean contrastive / zero-shot CE + feature consistency。
5. 与 vanilla FT、PAR、CleanCLIP 对比 rebound curve。

**预期现象**：endpoint ASR 可能接近 baseline，但 AURC 更低。  
**成功判据**：相比最强 baseline，AURC 降低 > 25%，clean drop < 3 pp。  
**风险诊断**：

- 若 utility drop 大：降低 OSA step/rank，冻结 early layers，加 trust region。
- 若 ASR_now 降低但 rebound 仍高：加入 anti-rebound objective。
- 若 endpoint 不降：subspace identification 错误或 proxy 不准。

## P5. Anti-rebound objective 验证

**实验目的**：验证 anti-rebound 是独立有效贡献。  
**实验流程**：

1. 固定 subspace identification 与 reprojection。
2. 对比：
   - no anti-rebound；
   - exact 3-step unroll；
   - first-order gradient alignment；
   - engineering version with stop-gradient inner FT。
3. horizon 测试 1/5/10/20/50。
4. 统计 ASR_now、max ASR、AURC、cost。

**预期现象**：anti-rebound 对 endpoint ASR 提升有限，但明显降低 long-horizon rebound。  
**成功判据**：AURC 降低 > 15–30%，max ASR 降低 > 20 pp，计算成本 < 2–3 倍。  
**风险诊断**：

- 若 exact unroll 成本太高：转一阶版。
- 若一阶版不稳定：使用 gradient clipping、cosine penalty、small k。
- 若 proxy-dependent：加入 proxy-free worst-case objective。

## P6. Retrieval task 验证

**实验目的**：证明方法不只是 closed-set classification trick。  
**实验流程**：

1. 模型：CLIP ViT-B/32 或 OpenCLIP ViT-B/32。
2. 数据：MSCOCO 5k / Flickr30K retrieval。
3. 攻击：target caption retrieval、target image retrieval、text trigger。
4. 防御：FT、CleanCLIP、InverTune、BasinBreaker-Lite。
5. 后续 clean retrieval fine-tuning。

**预期现象**：BasinBreaker 降低 I2T/T2I rebound ASR，同时保持 R@1/R@5/R@10。  
**成功判据**：retrieval AURC 降低 > 20%，R@1 drop < 2–3 pp。  
**风险诊断**：若 retrieval ASR 定义不稳定，用 target-rank / mean target similarity 作为连续指标。

## P7. Adapter-level persistent trigger

**实验目的**：验证供应链/LoRA setting。  
**实验流程**：

1. 冻结 CLIP base，训练 poisoned LoRA/adapter。
2. 触发器包括 visual patch、prompt phrase、semantic trigger。
3. 防御只允许访问 base + adapter。
4. 比较 reset adapter、LoRA clean FT、BasinBreaker on adapter subspace。
5. 后续 clean LoRA FT。

**预期现象**：简单 reset 对 adapter-level 后门有效但 utility 下降；BasinBreaker 更好平衡。  
**成功判据**：adapter ASR < 5–10%，clean utility drop < 2 pp，rebound AURC 低。  
**风险诊断**：如果 reset adapter 已完全解决，转为 appendix，并将主贡献聚焦 full-model persistent backdoor。

## P8. OpenCLIP scale sanity experiment

**实验目的**：测试是否可迁移到真实开源 CLIP 系列。  
**实验流程**：

1. 模型：OpenCLIP ViT-B/32。
2. 攻击：BadCLIP / patch / blended。
3. 防御：只做 BasinBreaker-Lite，不跑 heavy Hessian。
4. 任务：ImageNet-100 + MSCOCO retrieval。
5. 测试 20 epoch rebound。

**成功判据**：趋势与 OpenAI CLIP 一致，AURC 降低 > 15–20%。  
**风险诊断**：若 OpenCLIP 不明显，分析预训练数据/架构差异，放入 limitations。

---

# 5. 方法具体实现流程

## 5.0 BasinBreaker 总体算法

输入：

- poisoned model \(\theta_p\)
- clean calibration data \(\mathcal{D}_c\)
- optional clean reference \(\theta_{ref}\)
- optional trigger proxy generator \(\mathcal{G}_{proxy}\)
- adaptation horizon set \(\mathcal{H}\)
- suspect subspace rank \(r\)

输出：

- defended model \(\theta_d\)
- suspect subspace \(U\)
- layer-wise suspect scores
- defense trajectory logs

总体优化：

\[
\min_\theta
\mathcal{L}_{clean}(\theta)
+\lambda_{bd}\mathcal{R}_{bd}(\theta)
+\lambda_{ar}\mathcal{R}_{anti}(\theta)
+\lambda_{ret}\mathcal{L}_{ret}(\theta)
+\lambda_{avoid}\mathcal{R}_{avoid}(\theta;U,\theta_p)
+\lambda_{tr}\mathcal{R}_{trust}(\theta)
\]

其中：

- \(\mathcal{R}_{bd}\)：当前 backdoor risk surrogate；
- \(\mathcal{R}_{anti}\)：future adaptation 后的 backdoor risk；
- \(\mathcal{R}_{avoid}\)：避免回到 suspect basin；
- \(\mathcal{L}_{ret}\)：clean feature/zero-shot retention；
- \(\mathcal{R}_{trust}\)：限制参数偏移，防止 utility 崩溃。

伪代码：

```text
Algorithm BasinBreaker
Input: poisoned parameters theta_p, clean data D_c, rank r, horizons H
Output: defended parameters theta_d

1: Build clean batches B_c and proxy/suspect batches B_b
2: U, layer_scores <- IdentifySuspectSubspace(theta_p, B_c, B_b, r)
3: theta <- theta_p
4: for stage = 1 ... S_break do
5:     g_c <- grad L_clean(theta; B_c)
6:     g_b <- grad R_bd(theta; B_b)
7:     v <- ProjectToSuspectAndCleanOrthogonal(g_b, U, g_c)
8:     theta <- theta + alpha * NormalizeLayerwise(v)      # Orthogonal Sharpness Ascent
9:     theta <- ReprojectOrReset(theta, theta_p, theta_ref, U, gamma)
10:    theta <- StabilityConstrainedRecovery(theta, D_c, U, theta_p)
11: end for
12: theta_d <- AntiReboundTraining(theta, D_c, U, H)
13: return theta_d, U, layer_scores
```

---

## 5.1 Suspect Backdoor Subspace Identification

### 方案 A：基于 Hessian / Fisher 的曲率感知子空间识别

#### 输入

- model \(\theta_p\)
- clean data \(\mathcal{D}_c\)
- proxy trigger batches \(\mathcal{D}_b\)，由真实 trigger、trigger inversion、adversarial probing 或 UAP 生成
- candidate parameter blocks \(\mathcal{B}\)：projection head、late visual blocks、text projection、LayerNorm、MLP、attention、LoRA/adapter

#### 输出

- orthonormal basis \(U=[u_1,\ldots,u_r]\)
- layer-wise suspect score \(S_\ell\)
- curvature/sensitivity report

#### 核心定义

clean Hessian：

\[
H_c=\nabla_\theta^2 \mathcal{L}_{clean}(\theta_p)
\]

trigger-risk gradient covariance：

\[
C_b=\mathbb{E}_{B_b}[
\nabla_\theta \mathcal{R}_{bd}(\theta_p;B_b)
\nabla_\theta \mathcal{R}_{bd}(\theta_p;B_b)^\top]
\]

clean gradient covariance：

\[
C_c=\mathbb{E}_{B_c}[
\nabla_\theta \mathcal{L}_{clean}(\theta_p;B_c)
\nabla_\theta \mathcal{L}_{clean}(\theta_p;B_c)^\top]
\]

suspect direction score：

\[
Score(u)=
\frac{u^\top C_b u}
{\epsilon + |u^\top H_c u| + \beta u^\top C_c u}
\quad
\text{s.t. }\|u\|_2=1
\]

直觉：一个方向如果对 trigger risk 很敏感，但对 clean loss 的曲率和 clean gradient covariance 都小，就是 suspect。

求解可写成 generalized eigenproblem：

\[
C_b u = \lambda (H_c^{+}+\beta C_c+\epsilon I)u
\]

其中 \(H_c^{+}\) 可以用 Gauss-Newton/Fisher/diagonal Fisher 替代，避免 Hessian 非正定。

#### 实现细节

- 不对全参数做 dense Hessian。
- 对每个 block 单独估计 score：
  - projection head；
  - ViT last 2–4 blocks；
  - ResNet last stage；
  - LayerNorm affine；
  - MLP fc1/fc2；
  - attention q/k/v/o；
  - LoRA A/B matrices。
- 使用 Hessian-vector product：
  \[
  H_cv = \nabla_\theta \langle \nabla_\theta \mathcal{L}_{clean}, v\rangle
  \]
- 用 randomized Lanczos / block power iteration 求 top suspect directions。
- Fisher 近似：
  \[
  F_c=\mathbb{E}[\nabla \ell_c \nabla \ell_c^\top]
  \]
- 对每层做 layer-wise normalization：
  \[
  \tilde{u}_\ell = \frac{u_\ell}{\|\theta_\ell\|_2+\epsilon}
  \]

#### 复杂度

若 rank 为 \(r\)，Lanczos iteration 为 \(m\)，每次 HVP 成本约等于 1–2 次 backward：

\[
O(|\mathcal{B}| \cdot r \cdot m \cdot \text{Backward})
\]

CLIP ViT-B/32 可行；7B+ VLM 不适合全量 Hessian，只能对 adapter/LoRA/projector 或 block diagonal Fisher。

#### 适合参数模块

| 模块 | 优先级 | 原因 |
|---|---:|---|
| projection head | 高 | 后门常通过 embedding alignment 实现 |
| image encoder late blocks | 高 | visual trigger 与高层视觉特征相关 |
| LayerNorm affine | 高 | 小参数、大影响、易被 adapter/backdoor 利用 |
| MLP layers | 高 | 存储 shortcut/backdoor features |
| attention heads | 中 | semantic/text-trigger 可能相关 |
| text encoder | 中 | text/prompt trigger 必须考虑 |
| early visual layers | 低/中 | patch trigger 可能相关，但 reset 风险大 |
| LoRA/adapter weights | 极高 | adapter-level backdoor 首选 |

#### suspect direction 判定

一个方向 \(u\) 被判为 suspect，如果同时满足：

\[
u^\top C_b u \ge q_{0.9}(C_b),
\quad
u^\top C_c u \le q_{0.5}(C_c),
\quad
|u^\top H_c u| \le q_{0.5}(H_c),
\quad
\cos(u,g_c) \le \rho_c
\]

也可以用综合 score top-r。

---

### 方案 B：基于 trigger-sensitive gradient difference 的子空间识别

这是最推荐的主实现，因为它轻量、稳定、容易扩展。

#### 输入

- clean batch \(B_c=\{(x_i,t_i)\}\)
- proxy trigger batch \(B_b=\{(T_{\hat{\delta}}(x_i),t_{proxy})\}\)
- risk surrogate \(\mathcal{R}_{bd}\)

#### 输出

- \(U_g\)：gradient-difference subspace
- per-layer gradient energy

#### 核心计算

对每个 mini-batch：

\[
g_c^i=\nabla_\theta \mathcal{L}_{clean}(\theta;B_c^i)
\]

\[
g_b^i=\nabla_\theta \mathcal{R}_{bd}(\theta;B_b^i)
\]

\[
d_i = g_b^i - \Pi_{G_c}g_b^i
\]

其中 \(\Pi_{G_c}\) 是 clean gradient subspace projection：

\[
\Pi_{G_c}=G_c(G_c^\top G_c+\lambda I)^{-1}G_c^\top
\]

堆叠 \(D=[d_1,\ldots,d_m]\)，做 randomized SVD：

\[
D \approx U_g \Sigma V^\top
\]

取前 r 个方向。

#### 计算复杂度

\[
O(m \cdot \text{Backward} + r \cdot p)
\]

比 Hessian 方案便宜很多。可用于 OpenCLIP、LoRA、BLIP/ALBEF 的部分模块。

#### 如何构造 trigger proxy

已知 trigger setting：

\[
B_b=\{(T_\delta(x_i),y_t)\}
\]

未知 trigger setting：

1. **Universal adversarial probing**：优化小 patch 或 additive perturbation，使图像 embedding 向某些文本原型集中。
2. **Target discovery**：枚举 class prompts，找触发后 target concentration 最大的类别。
3. **InverTune-style inversion**：用 activation / gradient inversion 生成 proxy。
4. **Worst-case prompt probing**：寻找让模型预测分布低熵或跨样本一致的 perturbation。
5. **Synthetic semantic trigger**：用与目标文本无关的自然属性短语或图像贴片生成 suspect samples。

#### direction 判定

\[
Score_g(u_j)=
\frac{\sigma_j^2}
{\epsilon + \|U_c^\top u_j\|_2^2 + |u_j^\top H_c u_j|}
\]

若 \(Score_g\) 高且 layer energy 集中，则判为 suspect。

---

### 方案 C：基于 influence score / layer-wise sensitivity 的轻量版本

适用于大模型、快速 preliminary、资源有限场景。

#### 输入

- clean data
- proxy trigger data or adversarial probes
- candidate layer list

#### 输出

- layer-wise suspect score
- selected parameter mask \(M\)
- optional low-rank basis \(U_\ell\)

#### 核心分数

对 layer \(\ell\)：

\[
S_\ell=
\frac{
\mathbb{E}_{B_b}[\|\nabla_{\theta_\ell}\mathcal{R}_{bd}\|_2]
}{
\epsilon+
\mathbb{E}_{B_c}[\|\nabla_{\theta_\ell}\mathcal{L}_{clean}\|_2]
}
\cdot
\frac{1}{\epsilon+\widehat{\kappa}_{c,\ell}}
\]

其中 \(\widehat{\kappa}_{c,\ell}\) 可用 diagonal Fisher 或 local sharpness 近似：

\[
\widehat{\kappa}_{c,\ell}=
\mathbb{E}_{\xi_\ell}
\frac{\mathcal{L}_{clean}(\theta+\xi_\ell)-\mathcal{L}_{clean}(\theta)}
{\|\xi_\ell\|_2^2}
\]

也可加入 influence approximation：

\[
I_\ell(B_b,B_c)=
-\nabla_{\theta_\ell}\mathcal{R}_{bd}^\top
(H_{c,\ell}+\lambda I)^{-1}
\nabla_{\theta_\ell}\mathcal{L}_{clean}
\]

#### 复杂度

- 只需要 gradient norm + 少量 random perturbation；
- 可在 7B VLM adapter 上使用；
- 适合 BasinBreaker-Lite。

#### 适配模块

优先级：

1. LoRA/adapter weights；
2. projection heads；
3. LayerNorm affine；
4. MLP output projection；
5. attention output projection；
6. late visual/text blocks。

---

## 5.2 Orthogonal Sharpness Ascent

### 数学定义

定义 backdoor risk surrogate \(\mathcal{R}_{bd}(\theta)\)，越大代表越危险，例如 target confidence：

\[
\mathcal{R}_{bd}(\theta)=
\mathbb{E}_{x\sim\mathcal{D}_c,\hat{\delta}\sim\mathcal{G}_{proxy}}
\left[
\max_{c\in\mathcal{C}} p_\theta(c|T_{\hat{\delta}}(x))
\right]
\]

如果 target 已知：

\[
\mathcal{R}_{bd}(\theta)=
\mathbb{E}_{x}
p_\theta(y_t|T_{\hat{\delta}}(x))
\]

Orthogonal Sharpness Ascent 的目标是在 suspect subspace 内找到一个扰动 \(\Delta\)，使 backdoor risk 变得不稳定，同时 clean loss 不显著上升：

\[
\Delta^*=
\arg\max_{\Delta}
\mathcal{R}_{bd}(\theta+\Delta)-\mathcal{R}_{bd}(\theta)
-\mu[\mathcal{L}_{clean}(\theta+\Delta)-\mathcal{L}_{clean}(\theta)]_+
\]

约束：

\[
\Delta \in span(U),\quad
\|\Delta_\ell\|_2 \le \rho_\ell \|\theta_\ell\|_2,\quad
\langle \Delta,g_c\rangle=0
\]

注意这里 ascent 是对 “backdoor risk landscape 的不稳定性” 做上升，不是盲目增加 clean loss。

### 与 clean gradient 正交化

给定 backdoor risk gradient \(g_b=\nabla_\theta \mathcal{R}_{bd}\) 和 clean gradient matrix \(G_c=[g_c^1,\ldots,g_c^m]\)：

\[
\tilde{g}_b = U U^\top g_b
\]

\[
g_{\perp}=
\tilde{g}_b
-
G_c(G_c^\top G_c+\lambda I)^{-1}G_c^\top \tilde{g}_b
\]

若只用一个 clean gradient：

\[
g_{\perp}=
\tilde{g}_b-
\frac{\langle \tilde{g}_b,g_c\rangle}{\|g_c\|_2^2+\epsilon}g_c
\]

然后 layer-wise normalize：

\[
v_\ell =
\frac{g_{\perp,\ell}}
{\|g_{\perp,\ell}\|_2+\epsilon}
\cdot
\|\theta_\ell\|_2
\]

更新：

\[
\theta \leftarrow \theta + \alpha v
\]

### 步长选择

建议三层策略：

1. 初始：
   \[
   \alpha_\ell = \rho \frac{\|\theta_\ell\|_2}{\|v_\ell\|_2+\epsilon}
   \]
   \(\rho\in\{10^{-4},3\times10^{-4},10^{-3},3\times10^{-3}\}\)

2. line search：
   接受条件：
   \[
   \Delta \mathcal{L}_{clean} \le \eta_c
   \quad\text{and}\quad
   \Delta \mathcal{R}_{bd}\ge \eta_b
   \]

3. utility guard：
   如果 clean validation drop 超过阈值，回滚或减半步长。

### SAM/ASAM 风格近似

可以把 OSA 写成 SAM-style：

\[
\epsilon_b = \rho
\frac{P_{U,\perp c}(\nabla \mathcal{R}_{bd})}
{\|P_{U,\perp c}(\nabla \mathcal{R}_{bd})\|_2}
\]

然后做 recovery 时优化：

\[
\min_\theta
\mathcal{L}_{clean}(\theta)
+
\lambda
\mathcal{R}_{bd}(\theta+\epsilon_b)
\]

区别：SAM 通常 minimization sharpness；这里是对 backdoor risk 的 selective destabilization。

### 可实现伪代码

```text
function OrthogonalSharpnessAscent(theta, U, B_clean, B_proxy):
    g_c_list = [grad L_clean(theta; b) for b in B_clean]
    G_c = stack(g_c_list)
    g_b = grad R_bd(theta; B_proxy)

    g_s = U @ (U.T @ g_b)
    g_perp = g_s - G_c @ inv(G_c.T @ G_c + lambda I) @ G_c.T @ g_s

    for each layer l:
        g_perp[l] = g_perp[l] / (norm(g_perp[l]) + eps) * norm(theta[l])

    alpha = LineSearch(theta, g_perp, L_clean, R_bd)
    theta_new = theta + alpha * g_perp
    return theta_new
```

---

## 5.3 Subspace Reset / Reprojection

### 有 clean reference model 时

若有 \(\theta_{ref}\)，可以直接移除 poisoned model 与 reference 在 suspect subspace 的差异：

\[
\theta' =
\theta -
\gamma U U^\top(\theta-\theta_{ref})
\]

当 \(\gamma=1\)：

\[
\theta'=(I-UU^\top)\theta + UU^\top\theta_{ref}
\]

layer-wise 版本：

\[
\theta_\ell'=
\theta_\ell-
\gamma_\ell U_\ell U_\ell^\top(\theta_\ell-\theta_{ref,\ell})
\]

\(\gamma_\ell\) 根据 suspect score 设定：

\[
\gamma_\ell =
\min(\gamma_{max}, \gamma_0 \cdot \frac{S_\ell}{\text{median}(S)})
\]

### 没有 clean reference model 时

构造 reference subspace 的方式：

1. **Clean FT anchor**：先做短步 clean FT 得到 \(\theta_{cf}\)，但只用作 reference，不作为最终模型。
   \[
   \theta_{ref}=\theta_p-\eta\nabla \mathcal{L}_{clean}
   \]

2. **EMA clean anchor**：在 recovery 中维护 EMA：
   \[
   \theta_{ema}\leftarrow \beta\theta_{ema}+(1-\beta)\theta
   \]

3. **Clean-gradient null reference**：只约束更新不要进入 \(U\)：
   \[
   \theta'=\theta-UU^\top(\theta-\theta_{anchor})
   \]

4. **Synthetic clean adapters**：冻结 base，训练 clean adapter，作为 adapter subspace reference。

5. **Public pretrained CLIP reference**：若模型家族可知，可用同架构 public checkpoint，但只能作 optional setting。

### 只 reset adapter / LoRA / projection head 是否足够

- 对 adapter-level backdoor：通常足够，作为 strong baseline。
- 对 CLIP full-model backdoor：不一定足够，因为后门可能分布在 image encoder late blocks 和 projection head。
- 建议主方法支持 block-level mask：
  \[
  \mathcal{B}_{selected}=\{\ell:S_\ell>\tau_S\}
  \]

### 避免 catastrophic forgetting

加入 trust region：

\[
\mathcal{R}_{trust}=
\sum_{\ell}
\left[
\frac{\|\theta_\ell-\theta_{p,\ell}\|_2}
{\|\theta_{p,\ell}\|_2+\epsilon}
-\tau_\ell
\right]_+^2
\]

加入 feature consistency：

\[
\mathcal{L}_{feat}=
\mathbb{E}_{x\sim D_c}
\left[
1-\cos(z_I^\theta(x),z_I^{\theta_p}(x))
\right]
+
\mathbb{E}_{t\sim D_c}
\left[
1-\cos(z_T^\theta(t),z_T^{\theta_p}(t))
\right]
\]

但 feature consistency 不能过强，否则会把后门表示也保留下来。建议只在 clean samples 上做，并排除 suspect directions：

\[
\mathcal{L}_{feat}^{\perp U}=
\|(I-UU^\top)(h_\theta-h_{\theta_p})\|_2^2
\]

### reset 强度

超参数：

- \(\gamma\in\{0.1,0.3,0.5,0.7,1.0\}\)
- rank \(r\in\{5,10,20,50,100\}\)
- selected blocks top \(k\in\{1,2,4,8\}\)

选择标准：

- clean drop < 2 pp；
- endpoint ASR 降低；
- AURC 最低；
- layer-wise trust region 不超阈值。

---

## 5.4 Stability-constrained Recovery

### Recovery 阶段目标

\[
\mathcal{L}_{recover}=
\mathcal{L}_{clean}
+\lambda_{con}\mathcal{L}_{contrastive}
+\lambda_{zs}\mathcal{L}_{zero-shot-retain}
+\lambda_{feat}\mathcal{L}_{feature-consistency}
+\lambda_{param}\mathcal{R}_{param}
+\lambda_{avoid}\mathcal{R}_{avoid}
+\lambda_{ar}\mathcal{R}_{anti}
\]

实际可简化：

\[
\mathcal{L}_{recover}=
\mathcal{L}_{task}
+\lambda_{feat}\mathcal{L}_{feat}
+\lambda_{avoid}\|U^\top(\theta-\theta_{reset})\|_2^2
+\lambda_{margin}
\left[
m-\|U^\top(\theta-\theta_p)\|_2
\right]_+^2
\]

解释：

- 第一项恢复 clean utility；
- 第二项保持 clean representation；
- 第三项限制 recovery 重新沿 suspect subspace 移动；
- 第四项保持与原 poisoned basin 的投影距离。

### Clean loss 选择

zero-shot classification：

\[
\mathcal{L}_{CE}=
-\mathbb{E}_{(x,y)\sim D_c}
\log p_\theta(y|x)
\]

image-text contrastive：

\[
\mathcal{L}_{CLIP}=
-\frac{1}{N}
\sum_i
\log
\frac{\exp(s_\theta(x_i,t_i)/\tau)}
{\sum_j\exp(s_\theta(x_i,t_j)/\tau)}
+
-\frac{1}{N}
\sum_i
\log
\frac{\exp(s_\theta(x_i,t_i)/\tau)}
{\sum_j\exp(s_\theta(x_j,t_i)/\tau)}
\]

zero-shot retention：

\[
\mathcal{L}_{zs-retain}=
\mathbb{E}_{x\sim D_c}
KL(p_{\theta_p}(\cdot|x)\|p_\theta(\cdot|x))
\]

这要谨慎，因为 \(\theta_p\) 是 poisoned model；只在 clean images 上使用。

### Layer-wise freeze 策略

推荐默认：

- freeze early visual layers；
- allow projection head、LayerNorm、late visual blocks；
- text-trigger setting 允许 text projection + last text block；
- adapter setting 只更新 adapter + LayerNorm；
- recovery 后最后 1–2 epochs 只调 LayerNorm/projection head。

### 最终优化目标

\[
\theta_d=
\arg\min_{\theta\in\mathcal{T}(\theta_p)}
\left[
\mathcal{L}_{clean}(\theta)
+\lambda_{now}\mathcal{R}_{bd}(\theta)
+\lambda_{ar}
\mathbb{E}_{h\sim\mathcal{H}}
\mathcal{R}_{bd}(\mathcal{A}_h(\theta))
+\lambda_{avoid}\|U^\top(\theta-\theta_{reset})\|^2
+\lambda_{dist}
\left[m-\|U^\top(\theta-\theta_p)\|\right]_+^2
+\lambda_{feat}\mathcal{L}_{feat}
\right]
\]

---

## 5.5 Anti-rebound Objective

这是论文最关键部分。

### 5.5.1 Backdoor risk surrogate

如果 target 已知：

\[
\mathcal{R}_{bd}(\theta)=
\mathbb{E}_{x,\hat{\delta}}
p_\theta(y_t|T_{\hat{\delta}}(x))
\]

如果 target unknown：

\[
\mathcal{R}_{bd}^{unk}(\theta)=
\mathbb{E}_{x,\hat{\delta}}
\left[
\max_{c\in\mathcal{C}} p_\theta(c|T_{\hat{\delta}}(x))
-
p_\theta(\hat{y}_\theta(x)|T_{\hat{\delta}}(x))
\right]_+
\]

也可以用 concentration：

\[
\mathcal{R}_{conc}(\theta)=
-\mathbb{E}_{x,\hat{\delta}}H(p_\theta(\cdot|T_{\hat{\delta}}(x)))
\]

低 entropy / 高跨样本一致性代表潜在 backdoor target。

retrieval setting：

\[
\mathcal{R}_{bd}^{ret}(\theta)=
\mathbb{E}_{x,\hat{\delta}}
\max_{t\in\mathcal{T}_{cand}}
s_\theta(T_{\hat{\delta}}(x),t)
\]

### 5.5.2 精确版：unrolled optimization

定义未来 clean fine-tuning：

\[
\theta^{0}=\theta
\]

\[
\theta^{i+1}=
\theta^{i}
-\eta_i\nabla_{\theta^i}\mathcal{L}_{adapt}(\theta^i;B_i)
\quad i=0,\ldots,k-1
\]

anti-rebound loss：

\[
\mathcal{R}_{anti}^{exact}(\theta)=
\mathbb{E}_{k\in\mathcal{K},B_{0:k}}
\mathcal{R}_{bd}(\theta^k)
\]

最终：

\[
\min_\theta
\mathcal{L}_{recover}(\theta)
+\lambda_{ar}\mathcal{R}_{anti}^{exact}(\theta)
\]

优点：最贴合定义。  
缺点：二阶梯度成本高、显存高、长 horizon 不可行。

实现建议：

- k = 1/3/5；
- inner loop 使用小 batch；
- gradient checkpointing；
- first-order MAML approximation；
- truncated backprop；
- 每 n 个 outer steps 执行一次 anti-rebound。

### 5.5.3 一阶近似版：gradient alignment penalty

对 future adaptation 一阶展开：

\[
\mathcal{R}_{bd}(\theta-k\eta g_c)
\approx
\mathcal{R}_{bd}(\theta)
-
k\eta
\nabla\mathcal{R}_{bd}(\theta)^\top g_c
\]

由于 \(\mathcal{R}_{bd}\) 越大越危险，clean descent 会导致 rebound 的条件是：

\[
-\nabla\mathcal{R}_{bd}^\top g_c > 0
\quad\Leftrightarrow\quad
\nabla\mathcal{R}_{bd}^\top g_c < 0
\]

因此 penalize negative alignment：

\[
\mathcal{R}_{align}=
\left[
m-
\cos(\nabla\mathcal{R}_{bd},g_c)
\right]_+
\]

或：

\[
\mathcal{R}_{align}^{neg}=
\left[
-\frac{\nabla\mathcal{R}_{bd}^\top g_c}
{\|\nabla\mathcal{R}_{bd}\|\|g_c\|+\epsilon}
+\mu
\right]_+
\]

为了只关注 suspect subspace：

\[
\mathcal{R}_{align}^{U}=
\left[
-\frac{
(U^\top\nabla\mathcal{R}_{bd})^\top(U^\top g_c)
}{
\|U^\top\nabla\mathcal{R}_{bd}\|\|U^\top g_c\|+\epsilon
}
+\mu
\right]_+
\]

优点：便宜、稳定、适合大模型。  
缺点：只能近似短步 clean FT。

### 5.5.4 工程可行版：stop-gradient adaptation probe

伪代码：

```text
theta_probe = theta
for i in 1..k:
    g = grad L_clean(theta_probe; B_clean_i)
    theta_probe = stopgrad(theta_probe - eta_inner * g)

R_ar = R_bd(theta_probe; B_proxy)
loss = L_recover(theta) + lambda_ar * R_ar
```

为了让 outer loss 对 \(\theta\) 有梯度，可使用两种实现：

1. stop-gradient probe 只用于选择/更新 proxy 或 early stopping；
2. first-order MAML：不反传 Hessian，但保留 \(\partial \theta_k/\partial \theta \approx I\)。

推荐默认：

\[
\mathcal{R}_{anti}^{eng}=
\mathcal{R}_{bd}(\theta-\eta k \cdot stopgrad(g_c))
+
\lambda_{align}\mathcal{R}_{align}^{U}
\]

### 5.5.5 不依赖真实 trigger 的 anti-rebound

构造 worst-case rebound objective：

\[
\mathcal{R}_{bd}^{wc}(\theta)=
\max_{\delta\in\Delta, c\in\mathcal{C}}
\mathbb{E}_{x}
p_\theta(c|T_\delta(x))
\]

其中 \(\Delta\) 是可行 trigger family：

- small patch；
- alpha-blended texture；
- universal additive perturbation；
- semantic sticker/object；
- text phrase trigger；
- embedding-space perturbation。

工程上交替优化：

```text
for each outer step:
    delta <- UpdateProxyTrigger(theta, delta, clean batch)
    U <- update occasionally
    theta <- minimize clean + anti-rebound risk under delta
```

为了防止 proxy 过拟合，应使用多个 proxy families：

\[
\mathcal{R}_{bd}^{multi}=
\frac{1}{M}\sum_{m=1}^{M}
\mathcal{R}_{bd}(\theta;\hat{\delta}_m)
\]

### 5.5.6 最终推荐实现组合

主方法建议：

- subspace identification：方案 B + 方案 C；
- Hessian/Fisher：用于 analysis 与强版本；
- OSA：只对 top layers 与 projection head；
- reprojection：无 reference 默认用 clean anchor；
- anti-rebound：engineering version + alignment penalty；
- exact unroll：只做 ablation，不作为默认。

---

# 6. 主实验设计

## 6.1 模型

### 主实验模型

| 模型 | 角色 |
|---|---|
| CLIP RN50 | 低成本、ResNet 架构对照 |
| CLIP RN101 | ResNet scale-up |
| CLIP ViT-B/32 | 主力 ViT 模型 |
| CLIP ViT-B/16 | 更高分辨率 ViT，对 patch trigger 更敏感 |
| OpenCLIP ViT-B/32 | 开源训练分布差异 |
| OpenCLIP ViT-B/16 | open model scale-up |

### Appendix / 扩展模型

| 模型 | 是否建议 | 原因 |
|---|---|---|
| BLIP | 可选 | 生成/理解混合 VLP，验证泛化 |
| ALBEF | 可选 | 经典 VLP，对比结构不同 |
| SigLIP | 强 appendix | modern contrastive/sigmoid objective，不同 loss |
| LLaVA / MiniGPT-4 | stress test | 大 VLM 成本高，建议只做 adapter-level backdoor |

主论文建议先放 4 个模型：CLIP RN50、CLIP ViT-B/32、CLIP ViT-B/16、OpenCLIP ViT-B/32。其余放 appendix。

## 6.2 数据集

| 数据集 | 用途 |
|---|---|
| ImageNet-100 | 快速主实验、zero-shot classification、horizon sweep |
| ImageNet-1K | 最终主表，证明真实规模 |
| CIFAR-10/100 | sanity、低成本、多 target |
| MSCOCO | image-text retrieval、contrastive clean FT |
| Flickr30K | cross-dataset retrieval generalization |
| Visual Genome | dense visual concept / semantic trigger |
| Conceptual Captions subset / CC3M subset | poisoning / pretraining-style attack |
| ImageNet-R/A/Sketch | domain-shift clean adaptation |
| LAION subset | OpenCLIP-style clean adaptation appendix |

建议最小主矩阵：

- zero-shot：ImageNet-100 + ImageNet-1K；
- retrieval：MSCOCO + Flickr30K；
- cross-dataset：ImageNet-100 → CIFAR-100 / ImageNet-R，MSCOCO → Flickr30K。

## 6.3 攻击设置

### BadCLIP dual-embedding guided attack

- poison rate：0.1%、0.3%、0.5%、1%；
- target：banana / dog / car / arbitrary text target；
- trigger：optimized visual trigger；
- training data：CC3M/Conceptual Captions subset；
- evaluation：zero-shot ASR、retrieval ASR、defense evasion。

### BadCLIP++ / persistent variant

如果公开代码可用，直接复现。若不可用，实现核心组件：

- semantic-fusion micro-trigger；
- target-aligned subset selection；
- trigger embedding radius shrinkage；
- centroid alignment；
- parameter stability regularization / EWC；
- low-curvature basin regularization。

poison rate：0.3%、0.5%、1%。  
评估：defense 后 50 epoch clean FT，重点报告 AURC。

### Patch trigger

- BadNet-style square patch；
- size：4/8/16 pixels or 5% image area；
- location：corner / random；
- target：固定类别；
- poison rate：0.1–1%。

### Blended trigger

- pattern：noise/texture/watermark；
- alpha：0.05/0.1/0.2；
- target：固定类别；
- 用于测试低可见 trigger。

### Semantic trigger

- trigger：特定对象/属性，如 sunglasses、green patch、specific style；
- 可用 segmentation/mask 放置；
- 评估跨数据集泛化。

### Feature-space trigger

- 优化输入 perturbation 使 image embedding 接近 target text embedding；
- 更接近 CLIP threat；
- 适合 unknown-trigger stress test。

### Text-trigger / prompt-trigger

- 特定 token phrase 或 prompt pattern 触发 target；
- 需要 text encoder / prompt learning 攻击；
- 测试 text subspace identification。

### Adapter-level backdoor

- base CLIP frozen；
- poisoned LoRA rank 4/8/16；
- trigger 可以是 visual 或 text；
- 评估 defense 是否只需 adapter-space reset。

## 6.4 防御设置

### Clean data budget

分类：

- 16-shot/class；
- 64-shot/class；
- 128-shot/class；
- 1% train set；
- 5% train set。

retrieval：

- 1k / 5k / 10k / 50k clean image-text pairs。

### Defense epochs

- lightweight：1–3 epochs；
- default：5 epochs；
- strong：10 epochs；
- recovery：额外 1–3 epochs。

### Batch size

- CLIP RN50/ViT-B/32：128–256；
- ViT-B/16/OpenCLIP：64–128；
- retrieval contrastive：尽可能大 batch，或 gradient accumulation。

### Learning rate

- full FT：1e-6 / 5e-6 / 1e-5；
- projection head：1e-5 / 5e-5；
- prompt/LoRA：1e-4 / 5e-4；
- OSA step：relative norm 1e-4–1e-3。

### 参数更新范围

主设置：

- projection head；
- LayerNorm；
- last 2–4 visual blocks；
- optional last text block。

消融：

- full FT；
- LoRA-only；
- prompt-only；
- projection-only；
- global all-parameter。

### clean reference

主实验：无 clean reference。  
增强实验：public clean CLIP / OpenCLIP reference。  
oracle：same-architecture clean checkpoint。

### trigger knowledge

主实验：unknown trigger。  
oracle：known trigger and target。  
中间：trigger family known but pattern unknown。

## 6.5 持久性评估协议

### Post-defense adaptation set

对每个 defended model \(\theta_d\)，运行：

1. clean FT 1/5/10/20/50 epochs；
2. LR sweep：0.1x、1x、10x defense LR；
3. same-domain clean data；
4. domain-shift clean data；
5. LoRA FT rank 4/8/16；
6. partial-layer FT；
7. retrieval contrastive FT；
8. SWA/EMA；
9. parameter perturbation：
   \[
   \theta'=\theta_d+\sigma\frac{\|\theta_d\|}{\sqrt{p}}\epsilon
   \]
10. pruning / quantization；
11. checkpoint averaging：
   \[
   \theta_{avg}=\alpha\theta_d+(1-\alpha)\theta_{ft}
   \]

### 核心输出

- Rebound ASR curve；
- AURC；
- max ASR over horizons；
- Long-horizon Persistence Score；
- Utility-Stability Pareto Front；
- Defense Cost table。

---

# 7. 指标设计

## 7.1 攻击成功率指标

### ASR_now

\[
ASR_{now}=ASR(\theta_d)
\]

图表：主表 endpoint column。

### ASR_after_FT

\[
ASR_h=ASR(\mathcal{A}_h(\theta_d))
\]

图表：line plot，x-axis = adaptation epochs，y-axis = ASR。

### Max ASR over horizons

\[
ASR_{max}=\max_{h\in\mathcal{H}} ASR_h
\]

意义：防御最坏情况下是否可靠。

### AURC

\[
AURC=
\frac{1}{H}
\int_0^H ASR(t)dt
\]

离散用 trapezoid。  
意义：综合长期风险，比单点更稳。  
图表：bar chart + rebound curve。

### Rebound Ratio

\[
RR=
\frac{ASR_{max}-ASR_{now}}
{ASR(\theta_p)-ASR_{now}+\epsilon}
\]

意义：被压下去的后门有多少“弹回来”。

## 7.2 Clean utility 指标

### Zero-shot top-1/top-5

\[
Acc@1, Acc@5
\]

图表：utility vs ASR table。

### Retrieval R@K

\[
R@K = \mathbb{E}[\mathbb{1}\{rank(gt)\le K\}]
\]

报告 I2T 与 T2I 的 R@1/R@5/R@10。

### Image-text alignment

\[
Align=
\mathbb{E}_{(x,t)}
s_\theta(x,t)
-
\mathbb{E}_{(x,t^-)}
s_\theta(x,t^-)
\]

### Representation similarity

CKA：

\[
CKA(H_\theta,H_{\theta_p})
\]

或 clean feature cosine：

\[
\mathbb{E}_{x}\cos(z_I^\theta(x),z_I^{\theta_p}(x))
\]

### Calibration

Expected Calibration Error：

\[
ECE=\sum_b \frac{|B_b|}{n}|\text{acc}(B_b)-\text{conf}(B_b)|
\]

用于说明防御不是靠异常过度平滑。

## 7.3 稳定性指标

### Persistence Gap

\[
PG=
ASR_{max}-ASR_{now}
\]

### Rebound Slope

对 \(ASR_h\) 拟合线性或 log-linear：

\[
ASR_h = a + b\log(1+h)
\]

\(b\) 为 rebound slope。

### Basin Stability Score

在 suspect subspace 中采样扰动：

\[
BSS(\theta)=
\mathbb{P}_{\xi\sim\mathcal{N}(0,\sigma^2 UU^\top)}
[ASR(\theta+\xi)>\tau]
\]

越低越好。

### Curvature Change

\[
\Delta\kappa_U=
\text{Tr}(U^\top H_c(\theta_d)U)
-
\text{Tr}(U^\top H_c(\theta_p)U)
\]

以及 trigger-risk curvature：

\[
\Delta\kappa_{bd,U}=
\text{Tr}(U^\top H_{bd}(\theta_d)U)
-
\text{Tr}(U^\top H_{bd}(\theta_p)U)
\]

### Suspect subspace overlap

\[
Overlap(U_{pre},U_{post})=
\frac{1}{r}\|U_{pre}^\top U_{post}\|_F^2
\]

若 defense 成功，post-defense 后 suspect subspace 应显著变化。

### Clean/backdoor subspace angle

\[
Angle(U_b,U_c)=\arccos(\sigma_i(U_b^\top U_c))
\]

报告平均 principal angle。

## 7.4 代价指标

| 指标 | 定义 |
|---|---|
| Defense time | wall-clock time per model |
| GPU memory | peak memory |
| Clean data budget | number of clean samples / pairs |
| HVP count | Hessian-vector product 次数 |
| Backward count | normalized computation |
| Tuned parameter ratio | updated params / total params |
| Scalability | model size vs runtime/memory |
| Proxy optimization cost | trigger proxy steps |
| Storage cost | checkpoints / subspace basis size |

图表：cost-effectiveness Pareto，x = AURC，y = utility drop，marker size = GPU hours。

---

# 8. 消融实验设计

| Ablation | 证明什么 | 预期 | 失败时解释 |
|---|---|---|---|
| 去掉 subspace identification，随机方向 | suspect subspace 是否必要 | AURC 变高，utility 更差 | 若随机也有效，方法可能只是扰动正则；需改写贡献 |
| 去掉 OSA | basin-breaking 是否有效 | endpoint 可能相似，但 rebound 上升 | 若无差异，OSA 不是核心，弱化为 optional |
| 去掉 reprojection | reset 是否破坏稳定后门参数 | ASR_now 或 AURC 变差 | 若无差异，说明 recovery/anti-rebound 主导 |
| 去掉 anti-rebound loss | 长期稳定是否来自 anti-rebound | endpoint 相近，50 epoch ASR rebound | 若无差异，说明 subspace breaking 已够；重新定位 |
| suspect rank r | rank 敏感性 | r 太小不够，太大伤 utility | 若非常敏感，需 adaptive rank |
| clean data budget | 数据效率 | 小数据仍优于 baseline | 若需要大量数据，安全会议会质疑 practicality |
| k-step unroll | anti-rebound horizon | k=1/3 已有收益，k=5 稍强 | 若 k 越大越不稳定，采用一阶版 |
| Hessian vs Fisher vs gradient-diff | subspace 识别选择 | gradient-diff 性价比最高，Hessian 分析最好 | 若 Hessian 无优势，主方法用轻量版 |
| layer-wise vs global | 是否需要分层 | layer-wise utility 更好 | 若 global 更好，说明后门分散 |
| full FT vs LoRA-only | 更新范围影响 | LoRA utility 好但对 full backdoor 不足 | 若 LoRA 足够，主方法可更轻量 |
| with/without trigger proxy | unknown-trigger 可行性 | no-proxy 略弱但仍有效 | 若 no-proxy 失败，主 claim 需限制 |
| with/without clean reference | reference 依赖 | no-reference 应可工作 | 若强依赖 reference，threat model 变弱 |
| rebound horizon | 长期稳定 | 1/5/10/20/50 均优 | 若 50 epoch rebound，强调降低而非消除 |
| attack strength | 鲁棒范围 | poison rate 升高时逐步变难 | 若只弱攻击有效，不能投安全四大 |
| poison rate | 数据污染敏感性 | 0.1–1% 都有效 | 若高 poison 失败，作为 limitation |
| proxy family | 是否 overfit proxy | multi-proxy 泛化更好 | 若 overfit，需 worst-case objective |
| clean-gradient orthogonalization | 是否保护 utility | 无正交化 clean drop 更大 | 若无差异，简化算法 |
| trust region | 防止 forgetting | 无 trust region utility 下降 | 若无差异，减少复杂性 |

---

# 9. 理论分析方向

## 9.1 关键定义

### Persistent backdoor basin

给定 backdoor risk \(\mathcal{R}_{bd}\)、clean utility \(U\)、阈值 \(r,u\)，定义：

\[
\mathcal{B}_{bd}(r,u)=
\{\theta:
\mathcal{R}_{bd}(\theta)\ge r,\quad U(\theta)\ge u
\}
\]

如果 clean adaptation trajectory \(\theta_h=\mathcal{A}_h(\theta)\) 满足：

\[
\mathbb{P}[\exists h\le H:\theta_h\in\mathcal{B}_{bd}(r,u)]\ge p
\]

则称 \(\theta\) 有 \(H\)-horizon rebound risk。

### Clean-flat trigger-sensitive subspace

子空间 \(U\) 满足：

\[
\lambda_{max}(U^\top H_c U)\le \epsilon_c
\]

\[
\|U^\top \nabla \mathcal{R}_{bd}\|\ge \gamma_b
\]

\[
\|U^\top \nabla \mathcal{L}_{clean}\|\le \gamma_c
\]

则 \(U\) 是 clean-flat trigger-sensitive subspace。

## 9.2 为什么普通 clean FT 可能无法离开 basin

clean FT 更新：

\[
\theta_{t+1}=\theta_t-\eta g_c(\theta_t)
\]

若 basin 在 \(U\) 方向的边界距离为 \(d_U\)，且：

\[
\|U^\top g_c\|\le \gamma_c
\]

则 \(T\) 步后在 suspect subspace 的移动上界：

\[
\|U^\top(\theta_T-\theta_0)\|
\le
\eta T\gamma_c
\]

若 \(\eta T\gamma_c<d_U\)，则 clean FT 不足以离开 basin。

若 clean gradient 与 backdoor risk 呈 rebound alignment：

\[
\nabla\mathcal{R}_{bd}^\top g_c <0
\]

则 clean descent 会增加 backdoor risk：

\[
\mathcal{R}_{bd}(\theta-\eta g_c)
\approx
\mathcal{R}_{bd}(\theta)
-\eta\nabla\mathcal{R}_{bd}^\top g_c
>
\mathcal{R}_{bd}(\theta)
\]

这解释 BadCLIP++-style persistence。

## 9.3 为什么 sharpness ascent 可以降低 basin 稳定性

令 basin 半径定义为：

\[
rad_U(\theta)=
\sup\{\rho:
\forall \|\Delta\|\le \rho,\Delta\in span(U),
\mathcal{R}_{bd}(\theta+\Delta)\ge r\}
\]

如果 OSA 找到 \(\Delta\in U\) 使：

\[
\mathcal{R}_{bd}(\theta+\Delta)-\mathcal{R}_{bd}(\theta)\ge c_b
\]

同时在 recovery 后：

\[
\mathcal{R}_{bd}(\theta_{rec})\le r-\xi
\]

且 \(U\)-方向局部 Lipschitz 常数增大或 basin margin 减小，则需要更大的 clean FT alignment 才能回到 basin。直观上，OSA 不是为了最终停在 sharp point，而是为了暴露并破坏原后门宽盆地的稳定方向。

## 9.4 rebound bound 候选

### 定理候选 1：clean FT rebound 风险上界

假设：

1. \(\mathcal{R}_{bd}\) 在 trust region 内 \(L_b\)-smooth；
2. clean adaptation 每步梯度范数 \(\|g_c\|\le G\)；
3. BasinBreaker 后满足：
   \[
   \mathcal{R}_{bd}(\theta_d)\le r-\xi
   \]
4. anti-rebound alignment：
   \[
   \nabla\mathcal{R}_{bd}^\top g_c \ge -\alpha
   \]

则 \(T\) 步后：

\[
\mathcal{R}_{bd}(\theta_T)
\le
\mathcal{R}_{bd}(\theta_d)
+
\eta T\alpha
+
\frac{L_b}{2}\eta^2T G^2
\]

若右侧 < \(r\)，则不会 rebound 到 risk threshold。

证明思路：对 \(\mathcal{R}_{bd}(\theta-\eta g_c)\) 用 smoothness 展开并 telescoping。

### 定理候选 2：suspect-subspace avoidance 降低 re-entry probability

假设 adaptation update 的 suspect projection 是 sub-Gaussian：

\[
U^\top(\theta_T-\theta_d)\sim subG(\sigma^2T)
\]

若 BasinBreaker 使 defended point 与 backdoor basin 在 \(U\) 方向距离为 \(m\)，则：

\[
\mathbb{P}[\theta_T\in \mathcal{B}_{bd}]
\le
\exp\left(
-\frac{(m-\eta T\gamma_c)^2}{2\sigma^2T}
\right)
\]

证明思路：把 re-entry 事件转化为 suspect projection 超过 margin，用 concentration bound。

### 定理候选 3：subspace reprojection 降低 trigger risk 一阶项

若 backdoor risk 的主要梯度位于 \(U\)：

\[
\|(I-UU^\top)\nabla\mathcal{R}_{bd}\|\le \epsilon
\]

reprojection update：

\[
\theta'=\theta-\gamma UU^\top(\theta-\theta_{ref})
\]

则一阶 risk 变化：

\[
\mathcal{R}_{bd}(\theta')-\mathcal{R}_{bd}(\theta)
\approx
-\gamma \nabla\mathcal{R}_{bd}^\top UU^\top(\theta-\theta_{ref})
\]

若 reference 在 clean side，内积为正，则 risk 下降。

## 9.5 可视化验证方式

- 比较 \(\nabla \mathcal{R}_{bd}^\top g_c\) 在防御前后是否从负变正；
- 比较 \(U^\top(\theta_h-\theta_d)\) 随 horizon 是否被限制；
- 比较 \(rad_U\) 或 BSS 是否降低；
- 比较 AURC 与 theoretical bound 的相关性；
- 对不同攻击验证 \(\gamma_b,\gamma_c,\epsilon_c\)。

## 9.6 审稿人可能质疑点

| 质疑 | 回应 |
|---|---|
| 理论假设太局部 | 明确是 local trust-region analysis，并用可视化验证 |
| backdoor risk surrogate 不等于真实 ASR | 报告 surrogate-ASR correlation |
| sub-Gaussian update 不现实 | 作为分析工具，不作为严格 guarantee；附 empirical distribution |
| low-curvature 不是必要条件 | claim 改为 clean-flat / trigger-sensitive，允许异质性 |
| sharpness ascent 与 flat minima 理论冲突 | 强调只在 suspect subspace 上破坏 backdoor basin，不提高 clean loss sharpness |

---

# 10. 可视化与可解释性实验

## 10.1 Loss landscape / ASR landscape

生成方式：

- 选择两个方向：
  1. \(d_1 = \theta_d-\theta_p\)
  2. \(d_2 = U_1\) 或 PCA trajectory direction
- 网格：
  \[
  \theta(\alpha,\beta)=\theta_p+\alpha d_1+\beta d_2
  \]
- 计算 clean loss、trigger risk、ASR。

横轴：\(\alpha\)；纵轴：\(\beta\)；颜色：ASR 或 loss。  
预期：防御前有宽 backdoor basin；BasinBreaker 后 basin 变窄或偏移。

## 10.2 Clean basin 与 backdoor basin 二维投影

选择：

- clean FT trajectory；
- defended trajectory；
- rebound trajectory；
- BasinBreaker trajectory。

用 PCA/UMAP 投影参数差异。  
预期：baseline defense endpoint 离 backdoor basin 边界近，clean FT 后轨迹回到 basin；BasinBreaker 轨迹离开并保持距离。

## 10.3 曲率谱变化

计算：

- top eigenvalues of \(H_c\)；
- suspect subspace Rayleigh quotient；
- trigger-risk Hessian spectrum。

图：

- x-axis = eigen index；
- y-axis = eigenvalue/log eigenvalue；
- compare poisoned / baseline defended / BasinBreaker。

预期：BasinBreaker 改变 suspect subspace curvature，但不显著增加 clean top eigenvalues。

## 10.4 suspect subspace 与 clean subspace 夹角

图：

- x-axis = layer；
- y-axis = average principal angle；
- bars for attack types。

预期：后门相关层的 angle 更大，说明可分离；persistent attack 可能与 clean subspace 更对齐，解释难防。

## 10.5 Layer-wise suspect score heatmap

行：layers；列：signals（gradient sensitivity、Fisher inverse score、curvature、rebound influence）。  
颜色：normalized score。  
预期：projection head、late blocks、LayerNorm、adapter 权重高亮。

## 10.6 Rebound ASR curve

x-axis：post-defense adaptation epoch。  
y-axis：ASR。  
线：FT、CleanCLIP、InverTune、RVPT、PAR、BasinBreaker。  
预期：BasinBreaker endpoint 不一定最低，但曲线最低、最平。

## 10.7 Utility-ASR Pareto curve

x-axis：clean utility drop。  
y-axis：AURC 或 max ASR。  
点大小：defense cost。  
预期：BasinBreaker Pareto-dominates baselines。

## 10.8 Representation embedding visualization

用 t-SNE/UMAP 对 clean images、trigger images、proxy trigger images 的 embeddings 可视化。  
预期：

- poisoned：trigger samples 聚向 target text；
- baseline endpoint：暂时远离 target；
- baseline after FT：重新聚向 target；
- BasinBreaker：持续远离 target。

## 10.9 Trigger-sensitive neuron / attention head 分析

对每个 neuron/head 计算：

\[
S_j=
\frac{
|\mathbb{E}a_j(T(x))-\mathbb{E}a_j(x)|
}{
\epsilon+\text{Var}_{clean}(a_j)
}
\]

图：top neurons/heads before/after defense。  
预期：BasinBreaker 降低 trigger-specific activation。

## 10.10 Defense trajectory in parameter space

画出：

\[
\|U^\top(\theta_t-\theta_p)\|,\quad
\|(I-UU^\top)(\theta_t-\theta_p)\|
\]

随 defense/recovery/adaptation 变化。  
预期：BasinBreaker 显著增加 suspect-direction distance，并在 clean FT 后保持。

---

# 11. 工程实现计划

## 11.1 推荐代码结构

```text
project/
  attacks/
    badclip/
    badclip_plus/
    patch.py
    blended.py
    semantic.py
    feature_space.py
    text_trigger.py
    adapter_backdoor.py

  defenses/
    basinbreaker/
      identify_subspace.py
      hessian_fisher.py
      gradient_diff.py
      influence_score.py
      osa.py
      reprojection.py
      recovery.py
      anti_rebound.py
      lite.py
    baselines/
      cleanclip.py
      invertune.py
      rvpt.py
      par.py
      ibau.py
      anp.py
      nad.py
      bdetclip.py

  models/
    clip_wrapper.py
    openclip_wrapper.py
    blip_wrapper.py
    siglip_wrapper.py
    lora_utils.py
    parameter_blocks.py

  data/
    imagenet.py
    cifar.py
    mscoco.py
    flickr30k.py
    cc3m.py
    prompts.py
    trigger_transforms.py

  eval/
    asr.py
    zero_shot.py
    retrieval.py
    rebound_protocol.py
    utility.py
    cost.py
    calibration.py

  analysis/
    curvature.py
    landscape.py
    subspace_angles.py
    layer_heatmap.py
    trajectory.py
    cka.py
    visualization.py

  configs/
    attacks/
    defenses/
    models/
    datasets/
    rebound/
    ablations/

  scripts/
    run_attack.sh
    run_defense.sh
    run_rebound.sh
    run_ablation.sh
    run_analysis.sh

  checkpoints/
    poisoned/
    defended/
    rebound/
    subspaces/

  logs/
    metrics/
    wandb/
    tables/

  tests/
    test_hvp.py
    test_asr.py
    test_subspace.py
    test_rebound.py
```

## 11.2 需要复现的攻击代码

优先级：

1. BadNet patch / blended：作为 sanity；
2. BadCLIP dual-embedding：主攻击；
3. BadCLIP++ persistent variant：核心攻击；
4. text-trigger / prompt-trigger：补 multimodal；
5. adapter-level backdoor：供应链；
6. semantic trigger：物理/自然触发扩展；
7. feature-space trigger：unknown-trigger proxy stress test。

## 11.3 defense module

BasinBreaker 模块：

- `identify_subspace.py`：统一接口，输出 U 和 layer scores；
- `gradient_diff.py`：主实现；
- `hessian_fisher.py`：HVP、Lanczos、Hutchinson；
- `influence_score.py`：lightweight layer score；
- `osa.py`：正交化、line search、layer normalization；
- `reprojection.py`：reference/no-reference reset；
- `recovery.py`：clean loss、feature consistency、avoidance；
- `anti_rebound.py`：unroll、first-order、engineering version；
- `lite.py`：无 Hessian、无 exact unroll 的大模型版。

## 11.4 Hessian-vector product / Fisher approximation

PyTorch HVP：

```python
loss = clean_loss(model, batch)
grads = torch.autograd.grad(loss, params, create_graph=True)
dot = sum((g * v_i).sum() for g, v_i in zip(grads, v))
hvp = torch.autograd.grad(dot, params, retain_graph=False)
```

注意：

- 使用 fp32 计算 HVP，避免 fp16 下数值不稳；
- 对每个 layer/block 单独 flatten；
- 使用 gradient checkpointing；
- Fisher diagonal：
  \[
  F_{diag}\approx \frac{1}{m}\sum_i g_i^2
  \]
- Hutchinson trace：
  \[
  Tr(H)\approx \frac{1}{K}\sum_k z_k^\top Hz_k
  \]
  \(z_k\) 使用 Rademacher random vector。

## 11.5 unrolled anti-rebound 实现

三个版本：

1. exact：
   - 保留 inner loop graph；
   - k ≤ 3；
   - 小 batch；
   - 高显存。

2. first-order：
   - `create_graph=False`；
   - 近似 \(\partial\theta_k/\partial\theta=I\)。

3. engineering：
   - inner adaptation 只生成 probe；
   - 使用 alignment penalty 传梯度；
   - 默认版本。

## 11.6 checkpoint 管理

每个 run 保存：

- poisoned checkpoint；
- defense endpoint；
- recovery checkpoints；
- rebound checkpoints at 1/5/10/20/50；
- subspace basis U；
- layer scores；
- proxy triggers；
- config YAML；
- git commit；
- random seeds；
- metrics JSONL。

命名：

```text
{model}_{attack}_{poison_rate}_{target}_{defense}_{budget}_{seed}/
```

## 11.7 记录实验

每个 step 记录：

- clean loss；
- clean utility；
- ASR_now；
- proxy risk；
- gradient alignment；
- \(\|U^\top(\theta-\theta_p)\|\)；
- curvature estimate；
- GPU memory；
- wall time。

最终表格自动生成：

- main endpoint table；
- rebound table；
- AURC table；
- utility-cost table；
- ablation table。

## 11.8 可复现性

- 固定 seed：0/1/2/3/4；
- 报告均值 ± std；
- 所有 configs 入库；
- 公开 trigger generation code；
- 对每个数据集使用固定 subset indices；
- 记录 package versions；
- 提供 docker/conda env；
- HVP 使用 deterministic mode 时报告性能差异。

## 11.9 硬件预算

Preliminary：

- 1×A100 40GB 或 1×RTX 4090；
- CLIP RN50 / ViT-B/32；
- ImageNet-100 / MSCOCO 5k。

Main：

- 4×A100 80GB 更稳；
- ViT-B/16、OpenCLIP、多 seed、多 horizon；
- Hessian/Fisher analysis 建议单独跑。

大 VLM appendix：

- 只做 LoRA/adapter；
- 8-bit/4-bit loading；
- 不做 full Hessian。

## 11.10 Sanity check

1. clean CLIP + trigger 的 ASR 应接近随机；
2. poisoned CLIP clean accuracy 不应显著下降；
3. trigger proxy 应能提高 target confidence；
4. random subspace 不应稳定降低 ASR；
5. OSA 单步不应导致 clean loss 爆炸；
6. recovery 后 clean utility 应恢复；
7. HVP 与 finite difference 在小模型上对齐；
8. unrolled anti-rebound 的 k=0 等价 no anti-rebound；
9. seed variance 不应过大；
10. detection-only baseline 不应与 purification baseline 混评。

---

# 12. 阶段性研究计划

## Phase 0: Literature and codebase preparation

目标：建立可靠论文与代码基线。  
任务：

- 整理 CLIP backdoor attack/defense 文献；
- 复现 CleanCLIP、BadCLIP、基础 patch/blended；
- 搭建统一 ASR/CA/retrieval/rebound evaluation；
- 确认 baseline 的会议状态和代码许可。

产出：

- 文献表；
- 可运行 attack-defense pipeline；
- baseline config；
- evaluation scripts。

风险：

- BadCLIP++ 代码不可用；
- baseline 复现不一致。

Go/no-go signal：

- 至少复现 2 个攻击 + 2 个防御；
- ASR/CA 与论文或合理预期接近。

## Phase 1: Reproduce persistent rebound phenomenon

目标：证明问题真实存在。  
任务：

- 对 FT/CleanCLIP/InverTune/RVPT/PAR 运行 post-defense adaptation；
- 绘制 rebound ASR curve；
- 测试不同 LR、horizon、domain shift。

产出：

- Motivation figure；
- AURC table；
- endpoint vs long-horizon 对比。

成功标准：

- 至少一个强 baseline endpoint ASR 低但 long-horizon rebound 明显；
- persistent attack 比普通 trigger 更顽固。

Go/no-go signal：

- 若无 rebound，转向系统评估 “when do backdoors rebound?”；
- 若 rebound 明显，继续几何验证。

## Phase 2: Validate geometry hypothesis

目标：验证 clean-flat / trigger-sensitive subspace。  
任务：

- gradient-difference SVD；
- Fisher/Hessian estimates；
- layer-wise suspect score；
- principal angle；
- trajectory projection。

产出：

- geometry motivation figures；
- subspace separability table；
- layer heatmap。

成功标准：

- suspect directions 与 clean directions 可分离；
- suspect score 与 rebound risk 有相关性；
- persistent attacks 的 basin stability 更强。

Go/no-go signal：

- 若几何信号不稳定，主方法转向 empirical anti-rebound defense；
- 若信号稳定，进入 BasinBreaker v1。

## Phase 3: Implement BasinBreaker v1

目标：实现轻量可用版本。  
任务：

- gradient-difference subspace；
- OSA；
- no-reference reprojection；
- stability-constrained recovery；
- first-order anti-rebound。

产出：

- BasinBreaker-Lite；
- preliminary comparison table；
- ablation no anti-rebound/no OSA。

成功标准：

- AURC 比最强 baseline 降低 > 20–30%；
- clean drop < 3 pp；
- cost 可接受。

Go/no-go signal：

- 若收益来自 anti-rebound，弱化 OSA；
- 若 utility 损害大，缩小更新模块。

## Phase 4: Full main experiments

目标：形成主实验矩阵。  
任务：

- 4–6 个模型；
- 5–7 类攻击；
- 2–4 个数据集；
- 1/5/10/20/50 horizon；
- 多 seed；
- 强 baseline 全量对比。

产出：

- main tables；
- rebound curves；
- Pareto plots；
- cost analysis。

成功标准：

- 多模型、多攻击、多任务稳定优于 baselines；
- endpoint 与 long-horizon 都有优势；
- unknown-trigger setting 可用。

Go/no-go signal：

- 若只对 BadCLIP++ 有效，定位为 persistent-specific defense；
- 若泛化强，冲安全四大/NeurIPS。

## Phase 5: Ablation, theory, visualization

目标：把故事讲完整。  
任务：

- 完成 15 项 ablation；
- 写理论假设和定理；
- 生成 landscape、curvature spectrum、layer heatmap、trajectory；
- 完成 failure analysis。

产出：

- ablation table；
- theory section；
- visualization figures；
- limitations。

成功标准：

- 每个组件都有清晰作用；
- anti-rebound 是核心贡献；
- 理论与实验指标相关。

## Phase 6: Paper writing and rebuttal preparation

目标：投稿级论文。  
任务：

- introduction 强化问题定位；
- related work 对比 endpoint defense；
- method 精简但完整；
- evaluation 加 stress tests；
- 准备 reviewer attack list。

产出：

- full paper draft；
- appendix；
- artifact package；
- rebuttal FAQ。

Go/no-go signal：

- 若 reviewer 最可能问题都有实验支撑，即可投稿；
- 若 baseline 不完整，先补强 baseline。

---

# 13. 预期结果标准

## 13.1 最低可投稿标准

适合 workshop、二线会议、初版 arXiv：

- 模型：至少 CLIP RN50 + CLIP ViT-B/32；
- 攻击：至少 BadCLIP + patch + blended + persistent variant；
- 数据：ImageNet-100 + MSCOCO/Flickr30K；
- horizon：1/5/10/20 epochs；
- 相比最强 baseline：
  - AURC 降低 ≥ 25%；
  - max rebound ASR 降低 ≥ 20 pp；
  - clean accuracy drop ≤ 3–5 pp；
- unknown trigger setting 至少有一组可行；
- 消融证明 anti-rebound 有独立贡献。

## 13.2 强顶会标准

适合 NeurIPS/ICML/ICLR/CVPR security track：

- 模型：4–6 个 CLIP/OpenCLIP backbone；
- 攻击：BadCLIP、BadCLIP++/persistent、patch、blended、semantic、feature-space、text-trigger；
- 数据：ImageNet-1K/ImageNet-100、CIFAR-100、MSCOCO、Flickr30K；
- horizon：1/5/10/20/50 epochs；
- 相比最强 baseline：
  - AURC 降低 ≥ 40–60%；
  - 50 epoch max ASR 控制在 ≤ 10–15%；
  - clean utility drop ≤ 2–3 pp；
  - retrieval R@1 drop ≤ 2–3 pp；
- 无 clean reference 的主 setting 有效；
- trigger-unknown setting 有效；
- 包含 cost/Pareto；
- 理论分析与可视化充分。

## 13.3 安全四大强竞争力标准

适合 IEEE S&P / USENIX Security / CCS / NDSS：

- 明确指出现有防御评估漏洞，并系统复现 endpoint-low / rebound-high 现象；
- 至少 6 个模型或架构变体；
- 至少 7 类攻击，包括 adaptive/persistent/adapter-level；
- 至少 4 类 post-defense adaptation；
- 50 epoch long-horizon 必须有；
- 跨数据集和 retrieval 必须有；
- 相比最强 baseline：
  - AURC 降低 ≥ 50–70%；
  - max rebound ASR 降低 ≥ 40 pp；
  - 强 persistent attack 下 50 epoch ASR ≤ 10%；
  - clean drop ≤ 2 pp；
  - defense cost ≤ 2–4× 最强 purification baseline，或提供 BasinBreaker-Lite；
- 含 adaptive attacker analysis：
  - attacker 知道 BasinBreaker 后使用 higher curvature 或 clean-sensitive backdoor；
  - 报告失败边界；
- 代码、协议、指标可复现；
- limitations 诚实，negative findings 可解释。

---

# 14. 可能失败模式与备选方案

| 失败模式 | 诊断 | 改进 | 论文贡献转换 | 是否可写 negative finding |
|---|---|---|---|---|
| 后门不对应低曲率子空间 | suspect directions clean curvature 不低 | 改为 clean-flat/trigger-sensitive，多信号 score | 从“低曲率”转“稳定子空间” | 是，说明 low curvature 不充分 |
| Hessian 估计不稳定 | 不同 seed/eigenvectors 差异大 | Fisher、gradient covariance、block-wise | 主方法用轻量版，Hessian 做分析 | 是 |
| OSA 损害 utility | clean loss/Acc 大幅下降 | 小 rank、小步长、trust region、只 top blocks | OSA 变 optional | 是 |
| anti-rebound 成本高 | 显存/时间超预算 | 一阶 alignment、stop-gradient probe、k=1/3 | 提出 scalable surrogate | 是 |
| trigger proxy 不准确 | proxy risk 与真实 ASR 低相关 | multi-proxy、target discovery、worst-case UAP | 重点转 unknown-trigger proxy framework | 是 |
| 只对 BadCLIP++ 有效 | patch/blended/semantic 效果弱 | 分 attack family 调参；增加 generic recovery | 定位 persistent-specific defense | 可，但主标题要改 |
| baseline 过强优势不明显 | InverTune/RVPT endpoint + rebound 都强 | 强化 protocol：domain shift、LoRA、50 epoch | 贡献转 evaluation + analysis | 是 |
| 长期 FT 后仍 rebound | 50 epoch ASR 回升 | 报告降低 rebound 而非消除；加 periodic defense | 定义 lifecycle defense | 是 |
| clean reference 不可用 | no-reference 效果差 | clean anchor/EMA/synthetic adapters | reference-free variant 是贡献 | 是 |
| 大模型不可扩展 | HVP/全参数不可跑 | BasinBreaker-Lite on adapter/projector | scalable approximation | 是 |
| 后门与 clean feature 强耦合 | subspace angle 小，utility/ASR tradeoff 差 | prompt-level/output-level defense，拒绝高风险 inputs | impossibility-style analysis | 是，很有价值 |
| Adaptive attacker 绕过 | attacker 增大 clean-gradient alignment | 加 adaptive training baseline，报告边界 | arms-race discussion | 是 |

---

# 15. 最终论文故事线

## 15.1 Introduction 主线

建议结构：

1. **Multimodal foundation models are increasingly reused through fine-tuning and adapters.**
2. **Backdoor defenses for CLIP/VLP usually report endpoint ASR.**
3. **But persistent attacks change the game: a model can look clean immediately after defense and become dangerous again after benign adaptation.**
4. **Motivation experiment：InverTune/CleanCLIP/RVPT endpoint ASR low, but ASR rebounds after 10–50 epoch clean FT.**
5. **Why? Parameter geometry: persistent backdoors occupy clean-flat, trigger-sensitive subspaces stable under adaptation.**
6. **BasinBreaker: identify, break, reproject, recover, anti-rebound.**
7. **Results: lower AURC/max rebound ASR with small utility drop across attacks/tasks/models.**

## 15.2 Motivation experiment

Figure 1:

- Left：endpoint ASR bar，显示现有防御看起来有效；
- Right：rebound ASR curve，显示防御后 clean FT 反弹；
- Bottom：subspace projection trajectory，baseline 回到 backdoor basin，BasinBreaker 远离。

一句话：

> Endpoint ASR can be a misleading security metric.

## 15.3 Method section 组织

1. Problem formulation；
2. Suspect subspace identification；
3. Basin-breaking update；
4. Reprojection and recovery；
5. Anti-rebound objective；
6. Complexity and implementation variants。

建议正文只放主公式，详细 Hessian/Fisher/variants 放 appendix。

## 15.4 Evaluation section 组织

1. Experimental setup；
2. RQ1：Do existing defenses rebound?
3. RQ2：Does BasinBreaker reduce endpoint and rebound ASR?
4. RQ3：Does it preserve clean utility?
5. RQ4：How robust is it across attacks/models/tasks?
6. RQ5：Which component matters?
7. RQ6：What is the cost/scalability?
8. RQ7：What are the failure cases/adaptive attacks?

## 15.5 Theory / analysis section

建议放在 method 后或 evaluation 后：

- define clean-flat trigger-sensitive subspace；
- show clean FT rebound bound；
- show anti-rebound alignment bound；
- support with empirical gradient alignment and curvature figures。

不要过度承诺 formal guarantee。

## 15.6 Discussion 应强调

- BasinBreaker 不是万能 backdoor removal；
- 重点是从 endpoint purification 到 lifecycle stability；
- protocol 可独立用于评估其他 defense；
- geometry 工具可迁移到 LLM/VLM 后门；
- 大模型上应优先 adapter/projector-level deployment。

## 15.7 Limitations 写法

避免削弱贡献的表述：

> BasinBreaker does not claim to eliminate all possible adaptive persistent backdoors. Instead, it exposes and addresses a previously under-evaluated failure mode: post-defense rebound under benign adaptation. Its effectiveness depends on the separability between clean-sensitive and trigger-sensitive directions. When an attacker deliberately entangles the backdoor with essential clean features, any purification method faces an inherent utility-security trade-off, which our metrics make visible.

中文：

> 本文不声称可以消除所有自适应持久后门，而是提出并系统研究一个此前被低估的防御失败模式：防御后良性适配导致的后门反弹。BasinBreaker 的有效性依赖于 clean-sensitive 与 trigger-sensitive 方向存在一定可分离性；当攻击者有意将后门与核心 clean feature 绑定时，任何净化方法都会面临 utility-security trade-off。本文的协议和指标恰好可以量化这种边界。

## 15.8 论文标题备选

1. **BasinBreaker: Curvature-Aware Subspace Purification for Persistent Multimodal Backdoors**
2. **Beyond Endpoint ASR: Breaking Persistent Backdoor Basins in Multimodal Contrastive Models**
3. **When Backdoors Rebound: Persistence-Aware Defense for CLIP via Parameter-Space Basin Breaking**
4. **Defending CLIP Backdoors Over the Model Lifecycle: A Curvature-Aware Anti-Rebound Framework**
5. **From Backdoor Removal to Backdoor Stability: Subspace Geometry of Persistent Multimodal Backdoors**

## 15.9 摘要草稿

> Multimodal contrastive models such as CLIP are often distributed and repeatedly adapted through clean fine-tuning, prompt tuning, or lightweight adapters. Existing backdoor defenses for such models are typically evaluated at a single endpoint: whether the attack success rate (ASR) is reduced immediately after defense. In this paper, we show that this endpoint view can be misleading. Persistent multimodal backdoors may rebound after benign downstream adaptation, causing defended models to recover high ASR despite appearing safe initially. We provide a parameter-space explanation: persistent backdoors tend to occupy clean-flat yet trigger-sensitive subspaces that are weakly affected by ordinary clean fine-tuning. Based on this observation, we propose BasinBreaker, a persistence-aware defense that identifies suspect backdoor subspaces using curvature, gradient, and influence signals, selectively destabilizes them via orthogonal sharpness ascent, reprojects parameters away from the suspect basin, and explicitly optimizes an anti-rebound objective that simulates future clean adaptation. We further introduce a persistence-aware evaluation protocol with metrics such as rebound ASR, area under the rebound curve, and defense stability score. Across CLIP and OpenCLIP architectures, zero-shot classification and image-text retrieval tasks, and diverse visual, textual, semantic, feature-space, and adapter-level backdoors, BasinBreaker substantially reduces long-horizon rebound risk while preserving clean utility. Our results suggest that robust backdoor purification should be evaluated and optimized over the model lifecycle rather than at a single defense endpoint.

## 15.10 Contributions bullet points

建议最终版：

- **We identify post-defense rebound as a critical but under-evaluated failure mode of multimodal backdoor defenses.**  
  We propose a persistence-aware evaluation protocol covering clean fine-tuning, LoRA adaptation, domain shift, perturbation, quantization, and checkpoint averaging.

- **We provide a parameter-geometry analysis of persistent multimodal backdoors.**  
  We show that persistent backdoors exhibit clean-flat but trigger-sensitive subspaces that remain stable under ordinary clean adaptation.

- **We propose BasinBreaker, a curvature-aware subspace purification framework.**  
  BasinBreaker identifies suspect backdoor subspaces, breaks their basin stability, reprojects parameters away from them, and recovers clean utility under subspace avoidance.

- **We introduce anti-rebound training for backdoor defense.**  
  Instead of only minimizing current ASR, BasinBreaker explicitly minimizes future backdoor risk after simulated clean adaptation.

- **We conduct a comprehensive evaluation across models, attacks, tasks, and adaptation horizons.**  
  BasinBreaker improves long-horizon stability and utility-security Pareto trade-offs over strong multimodal and general backdoor defense baselines.

---

# 附录 A：推荐主实验表格模板

## A.1 Endpoint defense table

| Model | Attack | Defense | ASR_now ↓ | CA / R@1 ↑ | ΔUtility ↓ | Cost ↓ |
|---|---|---|---:|---:|---:|---:|

## A.2 Rebound table

| Model | Attack | Defense | ASR@0 | ASR@1 | ASR@5 | ASR@10 | ASR@20 | ASR@50 | AURC ↓ | Max ASR ↓ |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|

## A.3 Geometry table

| Model | Attack | Layer | Trigger Sensitivity ↑ | Clean Curvature ↓ | Clean Overlap ↓ | Suspect Score ↑ |
|---|---|---|---:|---:|---:|---:|

## A.4 Ablation table

| Variant | ASR_now | AURC | Max ASR | Clean Drop | HVP count | Time |
|---|---:|---:|---:|---:|---:|---:|

---

# 附录 B：建议优先级

## 第一优先级

1. 复现 rebound phenomenon；
2. 做 gradient-difference subspace；
3. 实现 BasinBreaker-Lite；
4. 证明 anti-rebound 降低 AURC；
5. 加 InverTune/CleanCLIP/RVPT/PAR 对比。

## 第二优先级

1. Fisher/Hessian analysis；
2. retrieval task；
3. OpenCLIP；
4. adapter-level backdoor；
5. 50 epoch long horizon。

## 第三优先级

1. BLIP/ALBEF/SigLIP；
2. LLaVA/MiniGPT-4；
3. adaptive attacker；
4. physical/semantic trigger；
5. formal theorem refinement。

---

# 附录 C：投稿前必须回答的 reviewer questions

1. 为什么不是普通 fine-tuning？
   - 用 no-subspace/no-anti-rebound ablation + FT baselines 回答。

2. 为什么不是 PAR 的复杂版？
   - PAR 没有 persistence-aware objective 和 suspect subspace geometry；用 AURC 和 rebound protocol 回答。

3. 为什么不是 InverTune 的后处理？
   - 可以把 BasinBreaker 加在 InverTune 后，证明互补；或者直接对比。

4. trigger unknown 怎么办？
   - multi-proxy + target discovery + worst-case concentration risk。

5. Hessian 太贵怎么办？
   - 主方法不用 heavy Hessian；Hessian 是 analysis/strong variant；BasinBreaker-Lite 可扩展。

6. 长期 50 epoch 后是否仍 rebound？
   - 报告而不是回避；目标是显著降低而非数学消除。

7. clean utility 是否被牺牲？
   - Pareto + trust region + feature consistency + retrieval R@K。

8. adaptive attacker 怎么办？
   - 增加 adaptive persistent attack，并给出边界分析。

9. 能否迁移到大 VLM？
   - adapter/projector-level 版本 + appendix。

10. 指标是否过多？
    - 主指标只保留 ASR_now、Max ASR、AURC、Clean Utility、Cost；其余分析用。

---

# 附录 D：文献锚点与 baseline 状态核查清单

投稿前应再次核查每篇方法的会议状态、代码、license 和复现设置。建议文献锚点：

- BadCLIP: Dual-Embedding Guided Backdoor Attack on Multimodal Contrastive Learning, CVPR 2024.
- BadCLIP: Trigger-Aware Prompt Learning for Backdoor Attacks on CLIP, CVPR 2024. 注意与 dual-embedding BadCLIP 同名不同工作。
- BadCLIP++: Stealthy and Persistent Backdoors in Multimodal Contrastive Learning, arXiv 2026.
- CleanCLIP: Mitigating Data Poisoning Attacks in Multimodal Contrastive Learning, ICCV 2023.
- InverTune: Removing Backdoors from Multimodal Contrastive Learning Models via Trigger Inversion and Activation Tuning, NDSS 2026.
- RVPT: Defending Multimodal Backdoored Models by Repulsive Visual Prompt Tuning, NeurIPS 2025 / arXiv version.
- BDetCLIP / Test-Time Multimodal Backdoor Detection by Contrastive Prompting.
- PAR: Perturb and Recover, arXiv 2024/2025; 若投稿前仍未正式接收，标为 emerging baseline。
- CBPT / Neural Antidote, arXiv 2025；若未正式接收，放 appendix。
- I-BAU, ICLR 2022.
- ABL, NeurIPS 2021.
- ANP, NeurIPS 2021.
- NAD, ICLR 2021，作为 legacy baseline。
- Selective Amnesia, IEEE S&P 2023.
- Redeem Myself, IEEE S&P 2023.
- MM-BD, IEEE S&P 2024.
- TED, IEEE S&P 2024.
- Exploring the Orthogonality and Linearity of Backdoor Attacks, IEEE S&P 2024，适合作为分析相关工作。

---

# 最终建议

这篇工作最稳的推进策略是：

1. **先证明 rebound 现象**，这是开题和投稿说服力的根；
2. **再证明几何信号与 rebound 相关**，不要一开始重投入 Hessian；
3. **先做 BasinBreaker-Lite**，用 gradient-difference + anti-rebound 拿到 AURC 改善；
4. **最后用 Hessian/Fisher/landscape/theory 提升论文深度**；
5. **主 claim 聚焦 persistence-aware lifecycle security**，不要承诺“完全消除所有后门”。

若 preliminary 结果显示：endpoint ASR 优势不明显，但 AURC、Max ASR、50 epoch stability 明显优于强 baseline，这仍然是非常好的顶会故事。因为本文要改变的是防御目标，而不是只刷新一个 endpoint ASR 数字。
