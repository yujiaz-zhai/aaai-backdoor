# BasinBreaker 论文前期方案规划提示词合集

本文件整理了用于规划 **BasinBreaker —— 面向持久性多模态后门的曲率感知子空间净化** 论文工作的完整提示词，可直接复制给大模型使用。

---

## 使用建议

建议先使用“主提示词”生成完整研究蓝图，再使用“算法细化提示词”进一步展开方法实现、数学定义、伪代码和工程框架。

如果希望输出质量更高，可以在主提示词前加入“严苛审稿人约束”。

---

## 提示词 0：严苛审稿人约束

```markdown
请你以严苛顶会审稿人和资深作者的双重视角回答：既要帮我把 idea 做成论文，也要主动指出哪些设计会被认为不严谨、不可复现、实验不充分或贡献不清晰。
```

---

## 提示词 1：主提示词 —— BasinBreaker 完整研究蓝图与实验路线

```markdown
你是一名长期从事多模态模型安全、后门攻击与防御、模型几何分析和顶级安全/AI会议论文写作的资深研究员。现在我准备基于如下 idea 开展一项完整论文工作，请你帮助我制定一套面向顶刊/顶会投稿标准的前期研究实施方案。

# 研究 Idea

论文暂名：BasinBreaker —— 面向持久性多模态后门的曲率感知子空间净化

核心问题：  
现有多模态后门防御方法往往只关注防御后当前时刻的 ASR 是否下降，但 persistent backdoor attack 可能使后门参数落入宽而稳定的低曲率盆地中。即使防御暂时压低 ASR，模型在后续 clean fine-tuning 后仍可能出现 ASR rebound。因此，本工作希望提出一种 persistence-aware defense：不只是抑制当前后门行为，而是识别后门所在的稳定参数子空间，并通过曲率感知、子空间破坏、重投影和 anti-rebound 训练，主动降低后门在后续 clean fine-tuning 中恢复的可能性。

核心假设：  
持久性多模态后门并非只表现为输入触发器层面的异常，而是在参数空间中形成了相对稳定、低曲率、对 clean utility 影响较小但对 trigger behavior 高敏感的 suspect backdoor subspace。若能识别并破坏该子空间，同时显式约束模型远离该后门盆地，则可以获得长期稳定的净化效果。

初步方法包括：
1. 识别 suspect backdoor subspace：
   - trigger proxy；
   - adversarial probing；
   - backdoor-sensitive mini-batches；
   - Hessian / Fisher / sharpness / influence score 估计；
   - 找出对 trigger 敏感、对 clean utility 不敏感、且处于低曲率稳定区域的方向。

2. Basin-breaking 更新：
   - Orthogonal Sharpness Ascent：沿近似正交于 clean-task 主梯度的方向提升后门子空间局部 sharpness，打破宽盆地；
   - Subspace Reset / Reprojection：将 suspect subspace 重投影到 clean reference subspace，或参考 clean model / clean adapters 做局部 reset；
   - Stability-constrained Recovery：用少量 clean data 恢复 clean utility，但约束模型不要回到 suspect basin。

3. Anti-rebound 训练：
   - 显式模拟未来 clean fine-tuning 过程；
   - 将 k-step clean fine-tuning 后的 ASR 或 trigger loss 写入防御目标；
   - 目标是不仅降低当前 ASR，还降低后续 fine-tuning 后的 rebound ASR。

# 你的任务

请你围绕这个 idea，制定一份完整、具体、可执行、面向顶刊/顶会标准的研究实施方案。请不要停留在概念层面，而要尽可能给出实验设计、实现流程、对比方法、消融实验、评价指标、风险控制、投稿故事线和预期结果标准。

请按照以下结构输出。

---

## 1. 论文定位与核心 scientific claim

请明确回答：

1. 这篇论文最核心的 scientific claim 应该是什么？
2. 它相对于现有多模态后门防御工作的本质区别是什么？
3. 它应该被包装成：
   - 一个新的 defense；
   - 一个新的 persistence-aware evaluation protocol；
   - 一个新的 parameter-geometry explanation；
   - 还是三者结合？
4. 顶会审稿人最可能认可的贡献点应该如何表述？
5. 这项工作最容易被质疑的地方是什么？应该提前如何规避？

请给出 3 个不同强度版本的 paper thesis：
- 保守版本；
- 标准顶会版本；
- 野心版本。

---

## 2. Threat model 与问题定义

请帮我严谨定义本文的 threat model 和 defense setting，包括：

1. 攻击者能力：
   - 是否能污染训练数据？
   - 是否能污染 fine-tuning 数据？
   - 是否能控制模型初始化或 checkpoint？
   - 是否使用 BadCLIP / BadCLIP++ / persistent backdoor / adapter-level backdoor？
2. 防御者能力：
   - 是否拥有 clean validation set？
   - 是否知道 trigger 类型？
   - 是否可以访问 poisoned model 的全部参数？
   - 是否允许有限 clean fine-tuning？
   - 是否有 clean reference model？
3. 防御目标：
   - 当前 ASR 降低；
   - clean utility 保持；
   - clean fine-tuning 后 ASR 不反弹；
   - 在不同 fine-tuning horizon 下稳定。
4. 明确排除哪些不现实或过强假设。
5. 给出形式化问题定义，包括：
   - 当前 ASR；
   - rebound ASR；
   - persistence gap；
   - defense stability；
   - clean utility drop。

请尽量使用论文中可以直接使用的数学符号。

---

## 3. Baseline 选择方案

请系统设计 baseline，而不是只列名, baseline 的选择必须是 安全四大或 顶刊定会已经发表的论文，且必须是5年内的论文工作，请分层说明：

### 3.1 基础 fine-tuning 类 baseline

包括但不限于：
- vanilla clean fine-tuning；
- linear probing；
- partial fine-tuning；
- layer-wise freezing；
- weight decay / L2 regularized fine-tuning；
- early stopping fine-tuning。

请说明这些 baseline 为什么必要，它们分别回答什么问题。

### 3.2 多模态后门防御 baseline

请列出适用于 CLIP / OpenCLIP / VLP models 的后门防御方法，例如：
- CLIP 后门净化相关方法；
- trigger inversion 类；
- prompt tuning / visual prompt tuning defense；
- representation purification；
- InverTune；
- 其他近年来多模态 backdoor defense。

对每个 baseline 请说明：
- 核心思想；
- 是否需要知道 trigger；
- 是否需要 clean data；
- 是否支持 black-box / white-box；
- 如何适配到本文 setting；
- 预期优劣。

### 3.3 通用后门防御 baseline

请考虑是否需要纳入：
- Neural Cleanse 类；
- Fine-Pruning 类；
- NAD 类；
- ANP / I-BAU / ABL / MCR 类；
- adversarial neuron pruning；
- mode connectivity / sharpness-based defenses。

请说明哪些应该纳入主实验，哪些放 appendix，哪些不适合多模态 setting。

### 3.4 持久性评估 baseline

请设计专门用于 persistence/rebound 的 baseline，包括：
- defense 后继续 clean fine-tuning；
- defense 后 domain shift fine-tuning；
- defense 后 parameter perturbation；
- defense 后 LoRA / adapter fine-tuning；
- defense 后 instruction-style 或 retrieval-style fine-tuning。

请说明这些 baseline 如何体现本文的必要性。

---

## 4. 前期验证性实验设计

请设计一组最小可行但有说服力的 preliminary experiments，用于验证这个方向是否值得继续投入。

要求包括：

1. 实验目标：验证什么核心假设？
2. 最小模型选择：
   - CLIP RN50；
   - CLIP ViT-B/32；
   - OpenCLIP ViT-B/32；
   - 是否需要更大模型？
3. 最小数据集选择：
   - ImageNet subset；
   - CIFAR-10 / CIFAR-100；
   - MSCOCO retrieval；
   - Flickr30K；
   - 是否需要 zero-shot classification 和 image-text retrieval 两类任务？
4. 攻击选择：
   - BadCLIP；
   - BadCLIP++；
   - simple patch trigger；
   - blended trigger；
   - semantic trigger；
   - feature-space trigger；
   - adapter-level persistent trigger。
5. 需要观察的现象：
   - 普通防御后 ASR 是否会 rebound；
   - 后门方向是否对应低曲率区域；
   - trigger-sensitive directions 与 clean-sensitive directions 是否可分离；
   - basin-breaking 是否能降低 rebound；
   - clean accuracy 是否保持。
6. 每个 preliminary experiment 的具体步骤、输入输出、成功标准和失败后的诊断方式。

请以“实验编号 + 实验目的 + 实验流程 + 预期现象 + 成功判据 + 风险诊断”的格式输出。

---

## 5. 方法具体实现流程

请将 BasinBreaker 设计成一个完整算法，包含数学目标、伪代码和实现细节。

### 5.1 Suspect Backdoor Subspace Identification

请设计至少 3 种可实现方案：

方案 A：基于 Hessian / Fisher 的曲率感知子空间识别  
方案 B：基于 trigger-sensitive gradient difference 的子空间识别  
方案 C：基于 influence score / layer-wise sensitivity 的轻量版本

每种方案请说明：
- 输入；
- 输出；
- 需要的数据；
- 计算复杂度；
- 是否适合大模型；
- 在 CLIP 中应该作用于哪些参数模块：
  - image encoder；
  - text encoder；
  - projection head；
  - normalization layers；
  - attention blocks；
  - MLP layers；
  - LoRA / adapter weights。
- 如何判断一个方向是 suspect direction。

### 5.2 Orthogonal Sharpness Ascent

请给出：
- 数学定义；
- 与 clean gradient 正交化的具体做法；
- sharpness ascent 的步长如何选；
- 如何避免损害 clean utility；
- 是否使用 SAM/ASAM 风格近似；
- 是否只在 suspect subspace 内进行；
- 是否需要 layer-wise normalization；
- 可实现伪代码。

### 5.3 Subspace Reset / Reprojection

请设计：
- 有 clean reference model 时如何重投影；
- 没有 clean reference model 时如何构造 reference subspace；
- 只 reset adapter / LoRA / projection head 是否足够；
- 如何避免 catastrophic forgetting；
- reset 强度如何调节；
- 是否需要 trust region 约束。

### 5.4 Stability-constrained Recovery

请设计 utility recovery 阶段：
- clean loss；
- contrastive loss；
- zero-shot retention loss；
- feature consistency loss；
- parameter distance regularization；
- suspect-subspace avoidance regularization；
- layer-wise freeze 策略。

请给出最终优化目标。

### 5.5 Anti-rebound Objective

请重点设计这一部分。要求包括：
- 如何近似 k-step clean fine-tuning；
- 是否使用 unrolled optimization；
- 是否使用 first-order approximation；
- 如何定义 rebound surrogate loss；
- 如何避免计算成本过高；
- 如何让该目标不依赖真实 trigger；
- 如果有 trigger proxy，如何使用；
- 如果没有 trigger proxy，如何构造 worst-case rebound objective；
- 最终 anti-rebound loss 的数学形式。

请至少给出：
- 精确版；
- 一阶近似版；
- 工程可行版。

---

## 6. 主实验设计

请设计完整主实验矩阵。

### 6.1 模型

至少考虑：
- CLIP RN50；
- CLIP RN101；
- CLIP ViT-B/32；
- CLIP ViT-B/16；
- OpenCLIP ViT-B/32；
- OpenCLIP ViT-B/16。

如有必要，请说明是否加入：
- BLIP；
- ALBEF；
- SigLIP；
- LLaVA / MiniGPT-4 等更大 VLM。

请说明主实验和 appendix 分别放哪些模型。

### 6.2 数据集

请覆盖：
- zero-shot classification；
- image-text retrieval；
- cross-dataset generalization。

候选数据包括：
- ImageNet；
- ImageNet-100；
- CIFAR-10 / CIFAR-100；
- MSCOCO；
- Flickr30K；
- Visual Genome；
- Conceptual Captions subset。

请说明每个数据集承担什么角色。

### 6.3 攻击设置

请至少包含：
- BadCLIP；
- BadCLIP++ 或 persistent variant；
- patch trigger；
- blended trigger；
- semantic trigger；
- feature-space trigger；
- text-trigger / prompt-trigger；
- adapter-level backdoor。

请说明每类攻击的 poison rate、trigger pattern、target class / target text、训练细节和评估方式。

### 6.4 防御设置

请明确：
- clean data budget；
- defense epochs；
- batch size；
- learning rate；
- 是否更新全部参数；
- 是否只更新部分层；
- 是否使用 LoRA；
- 是否使用 clean reference model；
- 是否已知 trigger；
- 是否未知 trigger。

### 6.5 持久性评估协议

请设计本文最重要的 evaluation protocol：

防御完成后，再进行多种后续 clean adaptation：

1. clean fine-tuning 1/5/10/20/50 epochs；
2. different learning rates；
3. different clean datasets；
4. LoRA fine-tuning；
5. partial-layer fine-tuning；
6. domain-shift fine-tuning；
7. stochastic weight averaging / EMA；
8. random parameter perturbation；
9. pruning / quantization 后的 persistence；
10. checkpoint averaging 后的 persistence。

请定义：
- Rebound ASR；
- Area Under Rebound Curve；
- Long-horizon Persistence Score；
- Utility-Stability Pareto Front；
- Defense Cost。

---

## 7. 指标设计

请提出一套比传统 ASR / CA 更完整的指标体系。

至少包括：

1. 攻击成功率：
   - ASR_now；
   - ASR_after_FT；
   - max ASR over horizons；
   - AURC: Area Under Rebound Curve。

2. Clean utility：
   - zero-shot top-1/top-5 accuracy；
   - retrieval R@1/R@5/R@10；
   - image-text alignment；
   - representation similarity；
   - calibration。

3. 稳定性指标：
   - Persistence Gap；
   - Rebound Slope；
   - Basin Stability Score；
   - curvature change；
   - suspect subspace overlap；
   - CKA / cosine similarity of representations。

4. 代价指标：
   - defense time；
   - GPU memory；
   - clean data budget；
   - number of Hessian-vector products；
   - scalability。

请给出每个指标的定义、计算方式、意义和可能的图表呈现方式。

---

## 8. 消融实验设计

请设计足够说服顶会审稿人的 ablation。

至少包括：

1. 去掉 subspace identification；
2. 去掉 orthogonal sharpness ascent；
3. 去掉 reprojection；
4. 去掉 anti-rebound loss；
5. 不同 suspect subspace 维度；
6. 不同 clean data budget；
7. 不同 k-step unroll 长度；
8. Hessian vs Fisher vs gradient-difference；
9. layer-wise vs global subspace；
10. full fine-tuning vs LoRA-only；
11. with vs without trigger proxy；
12. with vs without clean reference model；
13. 不同 rebound horizon；
14. 不同 attack strength；
15. 不同 poison rate。

请说明每个消融预期证明什么，失败时如何解释。

---

## 9. 理论分析方向

请提出一个可写进论文的理论分析框架，不要求完整证明，但要足够支撑方法动机。

请考虑：

1. 如何形式化 persistent backdoor basin；
2. 如何定义 low-curvature backdoor subspace；
3. 为什么普通 clean fine-tuning 可能无法离开该 basin；
4. 为什么 sharpness ascent 可以降低后门 basin 稳定性；
5. 为什么 suspect-subspace avoidance 可以降低 rebound probability；
6. 如何给出 rebound bound 或 persistence risk bound；
7. 是否可以基于局部二阶近似、mode connectivity、flat minima、influence function 或 stability theory 进行分析。

请输出：
- 关键假设；
- 定理候选；
- 证明思路；
- 可视化验证方式；
- 审稿人可能质疑点。

---

## 10. 可视化与可解释性实验

请设计帮助论文讲故事的可视化，包括：

1. loss landscape / ASR landscape；
2. clean basin 与 backdoor basin 的二维投影；
3. defense 前后曲率谱变化；
4. suspect subspace 与 clean subspace 的夹角；
5. layer-wise suspect score heatmap；
6. rebound ASR curve；
7. utility-ASR Pareto curve；
8. representation embedding visualization；
9. trigger-sensitive neuron / attention head 分析；
10. defense trajectory in parameter space。

请说明每个图应该如何生成，横纵轴是什么，预期现象是什么。

---

## 11. 工程实现计划

请给出一个从零开始的代码实现路线，包括：

1. 推荐代码结构；
2. 需要复现哪些攻击代码；
3. 需要实现哪些 defense module；
4. 如何实现 Hessian-vector product / Fisher approximation；
5. 如何实现 unrolled anti-rebound；
6. 如何管理 checkpoint；
7. 如何记录实验；
8. 如何保证可复现；
9. 需要的硬件预算；
10. 推荐先做哪些 sanity check。

请给出类似如下结构：

```text
project/
  attacks/
  defenses/
  models/
  data/
  eval/
  analysis/
  configs/
  scripts/
并说明每个模块的职责。

---

## 12. 阶段性研究计划

请给出一个分阶段 roadmap：

### Phase 0: Literature and codebase preparation

目标、任务、产出、风险。

### Phase 1: Reproduce persistent rebound phenomenon

目标、任务、产出、成功标准。

### Phase 2: Validate geometry hypothesis

目标、任务、产出、成功标准。

### Phase 3: Implement BasinBreaker v1

目标、任务、产出、成功标准。

### Phase 4: Full main experiments

目标、任务、产出、成功标准。

### Phase 5: Ablation, theory, visualization

目标、任务、产出、成功标准。

### Phase 6: Paper writing and rebuttal preparation

目标、任务、产出、成功标准。

请明确每个阶段应该优先完成什么，哪些结果是 go/no-go signal。

---

## 13. 预期结果标准

请明确这项工作最终需要达到什么程度，才有顶刊/顶会竞争力。

请分别给出：

1. 最低可投稿标准；
2. 强顶会标准；
3. 安全四大强竞争力标准。

请尽量量化，例如：

- 相比最强 baseline，rebound ASR 降低多少；
- clean accuracy drop 控制在多少以内；
- defense cost 允许增加多少；
- 在多少模型、多少攻击、多少数据集上有效；
- 是否需要未知 trigger setting；
- 是否需要长期 50 epoch rebound 测试；
- 是否需要跨攻击泛化。

---

## 14. 可能失败模式与备选方案

请系统分析该 idea 可能失败的原因，并给出 fallback。

至少包括：

1. 后门不一定对应低曲率子空间；
2. Hessian 估计不稳定；
3. sharpness ascent 损害 clean utility；
4. anti-rebound 计算成本太高；
5. trigger proxy 不准确；
6. 防御只对 BadCLIP++ 有效，泛化不足；
7. baseline 过强导致优势不明显；
8. 长期 fine-tuning 后仍然 rebound；
9. clean reference model 不可用；
10. 大模型上不可扩展。

对每个失败模式，请给出：

- 如何诊断；
- 如何改进；
- 如何转换论文贡献；
- 是否可以作为 negative finding 写入论文。

---

## 15. 最终论文故事线

请帮我设计论文叙事结构，包括：

1. Introduction 的主线；
2. Motivation experiment；
3. Method section 如何组织；
4. Evaluation section 如何组织；
5. Theory / analysis section 如何组织；
6. Discussion section 应该强调什么；
7. Limitations 如何写得不削弱贡献；
8. 论文标题备选；
9. 摘要草稿；
10. Contributions bullet points。

请给出一个适合安全四大 / NeurIPS / ICML 的写法。

---

# 输出要求

请用中文回答，但保留必要英文术语。  
请尽量具体、严谨、可执行，不要泛泛而谈。  
请把方案设计成“我可以直接拿去开题、写实验计划、搭代码和推进论文”的程度。  
如果你认为原始 idea 中有不合理、过强假设或容易被审稿人攻击的地方，请直接指出并给出改法。  
如果你认为还缺少某些关键实验、baseline、理论视角或 evaluation protocol，请主动补充。  
最终输出应该像一份完整的顶会论文研究蓝图，而不是普通头脑风暴。
```


```

---

## 提示词 2：附加强化要求 —— 实验设计解释质量

```markdown
请在每个实验设计后给出“为什么审稿人会认可这个实验”和“如果结果不理想，应该如何改写论文贡献”。
```

---

## 提示词 3：第二轮追问 —— 算法细化、数学定义与代码框架

```markdown
基于你刚才给出的研究蓝图，请进一步细化 BasinBreaker 的算法部分，给出完整数学定义、训练目标、伪代码、PyTorch 实现框架、关键超参数表，以及每个模块的可替代实现。

请重点展开以下内容：

## 1. 完整数学形式化

请形式化定义：
- poisoned multimodal model；
- clean data distribution；
- triggered data distribution；
- clean contrastive objective；
- attack success rate；
- rebound ASR；
- persistence gap；
- suspect backdoor subspace；
- clean-sensitive subspace；
- trigger-sensitive subspace；
- curvature-aware score；
- basin stability score。

要求符号统一，可以直接放进论文方法部分。

## 2. BasinBreaker 总体优化目标

请给出完整目标函数，至少包括：
- clean utility preservation loss；
- trigger suppression loss 或 trigger proxy loss；
- suspect subspace avoidance regularization；
- orthogonal sharpness ascent objective；
- reprojection / reset regularization；
- anti-rebound objective；
- feature consistency loss；
- parameter trust-region constraint。

请给出最终总损失：

L_total = ...

并解释每一项的作用、权重如何选择，以及哪些项用于不同 defense setting。

## 3. Suspect Backdoor Subspace Identification 细化

请分别给出三种实现：

### 3.1 Hessian / Fisher 版本
- 如何计算 Hessian-vector product；
- 如何用 Lanczos / power iteration 得到子空间；
- 如何区分 clean curvature 与 trigger curvature；
- 如何构造 suspect score；
- 如何选择 top-r directions。

### 3.2 Gradient-difference 版本
- 如何构造 clean batch 与 trigger-proxy batch；
- 如何计算 gradient difference；
- 如何用 SVD / randomized SVD 得到子空间；
- 如何降低显存开销；
- 如何进行 layer-wise aggregation。

### 3.3 Lightweight layer-wise 版本
- 如何定义 layer sensitivity；
- 如何定义 trigger-clean gradient ratio；
- 如何选择 suspicious layers；
- 如何只在 LoRA / adapter / projection head 中操作；
- 如何作为大模型版本的默认实现。

## 4. Orthogonal Sharpness Ascent 细化

请给出：
- 清晰的数学推导；
- 与 clean gradient 正交化公式；
- 如何限制在 suspect subspace；
- 如何选择 perturbation radius rho；
- 如何和 SAM / ASAM 区分；
- 如何避免 clean loss 爆炸；
- 伪代码；
- PyTorch 风格实现框架。

## 5. Subspace Reset / Reprojection 细化

请分别考虑：

### 有 clean reference model
- 如何计算参数差；
- 如何投影到 suspect subspace；
- 如何 reset；
- reset strength alpha 如何调节。

### 无 clean reference model
- 如何使用 EMA clean trajectory；
- 如何使用 early checkpoint；
- 如何使用 layer-wise mean statistics；
- 如何使用 clean feature anchors；
- 如何构造 self-reference。

### Adapter / LoRA setting
- 是否优先 reset low-rank matrices；
- 如何处理 rank collapse；
- 是否需要重新初始化部分 adapter；
- 如何防止 utility 下降。

## 6. Anti-rebound Objective 细化

请给出三个版本：

### 6.1 精确 unrolled 版本
- k-step clean fine-tuning；
- 如何反传 through optimization；
- 显存和时间复杂度；
- 何时适用。

### 6.2 一阶近似版本
- 如何用 Taylor approximation 近似未来参数；
- 如何估计 ASR rebound surrogate；
- 如何避免二阶开销。

### 6.3 工程可行版本
- 使用 periodic simulated fine-tuning；
- 使用 small clean minibatch；
- 使用 LoRA-only simulation；
- 使用 cached gradient；
- 使用 stop-gradient trick；
- 如何保证稳定。

请给出每个版本的伪代码和推荐默认设置。

## 7. 完整算法伪代码

请写出论文中可直接使用的伪代码，包括：

Algorithm 1: BasinBreaker Defense  
Algorithm 2: Suspect Subspace Identification  
Algorithm 3: Orthogonal Sharpness Ascent  
Algorithm 4: Anti-rebound Simulation

每个算法请包含：
- Input；
- Output；
- Main steps；
- Complexity note。

## 8. PyTorch 实现框架

请给出核心代码结构，而不是完整可运行代码即可。

至少包括：
- BasinBreakerDefense class；
- SubspaceEstimator class；
- SharpnessAscent module；
- Reprojection module；
- AntiReboundTrainer module；
- evaluate_rebound function；
- checkpoint 管理方式；
- config 示例。

请使用接近真实 PyTorch 的伪代码，便于我后续改成代码。

## 9. 默认超参数建议

请给出一张表，包括：
- suspect subspace rank；
- defense epochs；
- recovery epochs；
- learning rate；
- batch size；
- sharpness radius rho；
- reset strength alpha；
- anti-rebound unroll steps k；
- clean data budget；
- loss weights；
- Fisher / Hessian estimation steps；
- layer selection ratio。

请分别给出：
- CLIP RN50 默认配置；
- CLIP ViT-B/32 默认配置；
- OpenCLIP 默认配置；
- 大模型 / LoRA-only 默认配置。

## 10. 计算复杂度与工程优化

请分析：
- 时间复杂度；
- 显存复杂度；
- Hessian-vector product 数量；
- 与普通 fine-tuning 的 cost ratio；
- 哪些模块可以并行；
- 如何使用 mixed precision；
- 如何使用 gradient checkpointing；
- 如何用 low-rank approximation；
- 如何用 layer-wise local operation 降低成本。

## 11. 实现优先级

请按照研究推进顺序告诉我应该先实现什么：

1. 最小可行版本；
2. 可用于 preliminary result 的版本；
3. 可用于主实验的版本；
4. 可用于论文 release 的版本。

每个版本必须说明：
- 包含哪些模块；
- 暂时不包含哪些模块；
- 能验证什么；
- 成功标准是什么。

## 12. 审稿人可能攻击算法的点

请列出算法部分最容易被攻击的点，例如：
- 子空间定义是否主观；
- 曲率估计是否可靠；
- anti-rebound 是否只是 overfitting；
- trigger proxy 是否过强；
- clean reference 是否不现实；
- sharpness ascent 是否只是破坏模型；
- 方法是否太复杂。

对每一点，请给出论文中应如何防御，包括：
- 额外实验；
- 数学解释；
- ablation；
- discussion 写法。
```

---

## 推荐使用顺序

1. 先复制“提示词 0 + 提示词 1”，生成完整研究蓝图。
2. 如果输出中的实验部分不够强，再追加“提示词 2”。
3. 等研究蓝图稳定后，复制“提示词 3”，专门生成算法和实现细节。
4. 再根据输出继续追问：
   - baseline 复现优先级；
   - preliminary experiments 具体脚本；
   - paper outline；
   - related work 框架；
   - ablation 表格设计；
   - response-to-reviewer 预案。
