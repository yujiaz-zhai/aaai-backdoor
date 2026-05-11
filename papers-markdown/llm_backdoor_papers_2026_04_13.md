# 大模型后门攻击及防御技术论文汇总

> 搜索日期：2026-04-13
> 搜索主题：面向多模态触发与动态植入的大模型后门攻击及防御技术研究
> 标签：4.13

---

## 一、安全四大 (Big 4 Security Venues)

### 1. BAIT: Large Language Model Backdoor Scanning by Inverting Attack Target
- **发表场所**: IEEE S&P 2025
- **年份**: 2025
- **大类**: 后门检测
- **链接**: https://doi.org/10.1109/SP61157.2025.00103
- **总结**: 提出一种通过反转攻击目标来扫描LLM后门的技术BAIT。利用后门目标标记之间极强的因果关系，通过反转目标而非触发器来识别后门，大幅降低搜索空间，在仅需黑盒访问的情况下有效识别后门。在153个LLM、8种架构、6种攻击类型上验证，TrojAI竞赛LLM轮次排名第一。

### 2. Backdoor Defense via Test-Time Detecting and Repairing
- **发表场所**: CVPR 2024
- **年份**: 2024
- **大类**: 后门防御
- **链接**: https://doi.org/10.1109/CVPR52733.2024.02319
- **总结**: 提出在测试时检测并修复后门的框架，通过分析模型在正常样本和后门样本上的行为差异来识别后门，并在测试阶段进行修复，在保持模型正常性能的同时有效降低后门攻击成功率。

### 3. Devil in the Room: Triggering Audio Backdoors in the Physical World
- **发表场所**: USENIX Security 2024
- **年份**: 2024
- **大类**: 音频后门攻击
- **链接**: https://www.usenix.org/system/files/sec23winter-prepub-166-chen.pdf
- **总结**: 首次在物理世界中实现音频后门触发攻击，展示了如何在实际场景中通过播放特定音频触发器来激活后门，验证了音频后门攻击在物理世界的可行性。

### 4. InverTune: Backdoor Defense for Multimodal Contrastive Learning
- **发表场所**: NDSS 2026
- **年份**: 2026
- **大类**: 多模态后门防御
- **链接**: https://www.ndss-symposium.org/wp-content/uploads/2026-f1666-paper.pdf
- **总结**: 通过后门-对抗相关分析实现多模态对比学习的后门防御，建立后门触发器与对抗样本之间的联系，提出有效的防御机制。

---

## 二、人工智能/计算机顶会 (AI/ML Top Venues)

### 5. Probe before You Talk: Towards Black-box Defense against Backdoor Unalignment for Large Language Models
- **发表场所**: ACL 2025
- **年份**: 2025
- **大类**: LLM后门防御
- **链接**: https://arxiv.org/abs/2506.16447
- **总结**: 提出BEAT黑盒防御方法，通过探针拼接效应检测触发样本。该方法通过测量探针在拼接前后输出分布的失真程度来识别后门激活，无需模型参数、架构或干净参考数据即可进行推理时防御。

### 6. TCAP: Tri-Component Attention Profiling for Unsupervised Backdoor Detection in MLLM Fine-Tuning
- **发表场所**: AAAI 2026
- **年份**: 2026
- **大类**: 多模态LLM后门检测
- **链接**: https://arxiv.org/abs/2601.21692
- **总结**: 发现后门指纹——注意力分配发散现象，提出TCAP无监督防御框架。将跨模态注意力分解为系统指令、视觉输入和用户文本查询三个组件，通过高斯混合模型识别触发响应注意力头，实现无监督后门样本过滤。

### 7. ToT: Probing Semantic Insensitivity for Inference-Time Backdoor Defense in Multimodal Large Language Model
- **发表场所**: AAAI 2026
- **年份**: 2026
- **大类**: 多模态LLM推理时防御
- **链接**: https://doi.org/10.1609/aaai.v40i42.40891
- **总结**: 发现视觉触发器存在时文本变化敏感性显著降低的现象，提出ToT框架。通过对文本提示施加受控语义扰动并联合分析响应的一致性和置信度漂移，实现推理时后门检测。

### 8. BadLLM-TG: A Backdoor Defender powered by LLM Trigger Generator
- **发表场所**: AAAI 2026
- **年份**: 2026
- **大类**: 后门防御
- **链接**: https://arxiv.org/abs/2603.15692
- **总结**: 利用LLM的丰富知识生成触发器，通过提示驱动强化学习优化，使用受害者模型反馈损失作为奖励信号，生成的触发器用于对抗训练，平均降低攻击成功率76.2%。

### 9. Adversarial-Inspired Backdoor Defense via Bridging Backdoor and Adversarial Attacks
- **发表场所**: AAAI 2025
- **年份**: 2025
- **大类**: 后门防御
- **链接**: https://doi.org/10.1609/aaai.v39i9.33030
- **总结**: 发现对抗攻击在后门样本上的两个有趣现象：存在触发器时样本更难转化为对抗样本；后门样本的对抗样本容易被预测为真实标签。基于此提出AIBD方法，利用渐进式top-q方案和对抗标签隔离后门样本。

### 10. Speed Master: Quick or Slow Play to Attack Speaker Recognition
- **发表场所**: AAAI 2025
- **年份**: 2025
- **大类**: 语音后门攻击
- **链接**: https://doi.org/10.1609/aaai.v39i21.34367
- **总结**: 提出通过操纵语音速度来执行纯后门攻击的方法，利用平台允许调整播放速度的特性实现隐蔽攻击，在数字域达到99%以上攻击成功率，仅需0.6%污染率。

---

## 三、安全顶刊 (Security Journals)

### 11. Reverse Backdoor Distillation: Towards Online Backdoor Attack Detection for Deep Neural Network Models
- **发表场所**: IEEE TDSC 2024
- **年份**: 2024
- **大类**: 后门检测
- **链接**: https://doi.org/10.1109/TDSC.2024.3369751
- **总结**: 提出RBD在线后门检测方法，从可疑模型中蒸馏后门攻击模式知识创建影子模型，部署在线进行预测，节省至少97%计算量，在检测源特定攻击方面优于现有基准。

### 12. StealthPhase: Toward a Stealthy Backdoor Attack Against Speaker Recognition
- **发表场所**: IEEE TIFS 2025
- **年份**: 2025
- **大类**: 语音后门攻击
- **链接**: https://doi.org/10.1109/TIFS.2025.3642543
- **总结**: 将预定义触发器注入相位频谱实现隐蔽后门攻击，利用人耳对相位信息不敏感的特性，触发器在频谱可视化和听觉感知上几乎无法区分，同时达到99%攻击成功率和优秀的隐蔽性。

### 13. Stealthy Backdoor Attack Against Speaker Recognition Using Phase-Injection Hidden Trigger
- **发表场所**: IEEE LSP 2023
- **年份**: 2023
- **大类**: 语音后门攻击
- **链接**: https://doi.org/10.1109/LSP.2023.3293429
- **总结**: 提出PhaseBack方法，在相位频谱中注入触发器，利用人耳对相位信息不敏感的特性实现隐蔽攻击，在频域注入部分扰动导致时域全局扰动，实验证明有效且能绕过多种防御方法。

---

## 四、多模态后门攻击与防御 (Multimodal Backdoor Attack & Defense)

### 14. AnyDoor: Test-Time Backdoor Attacks on Multimodal Large Language Models
- **发表场所**: arXiv 2024
- **年份**: 2024
- **大类**: 多模态后门攻击
- **链接**: https://arxiv.org/abs/2402.08577
- **总结**: 提出测试时后门攻击AnyDoor，通过对抗测试图像（共享相同通用扰动）将后门注入文本模态，无需访问或修改训练数据。利用通用对抗攻击技术，但能够分离后门设置和激活的时机，可动态改变后门触发提示/有害效果。

### 15. BaThe: Defense against the Jailbreak Attack in Multimodal Large Language Models by Treating Harmful Instruction as Backdoor Trigger
- **发表场所**: arXiv 2024
- **年份**: 2024
- **大类**: 多模态LLM防御
- **链接**: https://arxiv.org/abs/2408.09093
- **总结**: 将有害指令视为后门触发器，提出BaThe防御机制。利用虚拟拒绝提示嵌入软文本嵌入（称为"楔子"），在不干扰正常性能的情况下有效缓解各种越狱攻击，并能适应防御未见攻击。

### 16. BadVision: Stealthy Backdoor Attack in Self-Supervised Learning Vision Encoders for Large Vision Language Models
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 多模态后门攻击
- **链接**: https://arxiv.org/abs/2502.18290
- **总结**: 发现只需损害视觉编码器即可在LVLMs中诱导视觉幻觉，提出BadVision方法。由于编码器的共享和复用，许多下游LVLMs可能继承后门行为，导致广泛后门。在两种SSL编码器和LVLMs上评估，攻击成功率超99%，当前最先进的检测方法无法有效检测。

### 17. UniGuardian: A Unified Defense for Detecting Prompt Injection, Backdoor Attacks and Adversarial Attacks in Large Language Models
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: LLM统一防御
- **链接**: https://arxiv.org/abs/2502.13141
- **总结**: 首次提出统一防御机制UniGuardian，检测LLM中的提示注入、后门攻击和对抗攻击。提出单次前向策略同时进行攻击检测和文本生成，优化检测流程。

### 18. E²AT: Multimodal Jailbreak Defense via Dynamic Joint Optimization for Multimodal Large Language Models
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 多模态越狱防御
- **链接**: https://arxiv.org/abs/2503.04833
- **总结**: 提出高效端到端对抗训练框架E²AT，针对视觉和文本对抗攻击。引入高效投影仪AT模块和动态联合多模态优化策略，在文本和图像模态上平均优于基线34%，同时保持干净任务性能。

### 19. Q-MLLM: Vector Quantization for Robust Multimodal Large Language Model Security
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 多模态安全
- **链接**: https://arxiv.org/abs/2511.16229
- **总结**: 通过两级向量量化整合Q-MLLM架构，创建离散瓶颈抵御对抗攻击，同时保持多模态推理能力。通过在像素-补丁和语义级别离散化视觉表示，阻断攻击路径，弥合跨模态安全对齐差距。

### 20. FC-Attack: Jailbreaking Multimodal Large Language Models via Auto-Generated Flowcharts
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 多模态越狱攻击
- **链接**: https://arxiv.org/abs/2502.21059
- **总结**: 发现使用部分有害信息的流程图可诱导MLLMs提供额外有害细节，提出FC-Attack攻击方法。通过微调LLM创建步骤描述生成器，生成对应有害查询的步骤描述，转换为流程图作为视觉提示，在Advbench上达到96%攻击成功率。

### 21. Natural Reflection Backdoor Attack on Vision Language Model for Autonomous Driving
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 自动驾驶多模态攻击
- **链接**: https://arxiv.org/abs/2505.06413
- **总结**: 针对自动驾驶场景中VLM系统的自然反射后门攻击，将类似玻璃或水的微弱反射模式嵌入图像，同时在相应文本标签前添加冗长无关前缀，诱导模型在遇到触发器时产生异常长的响应，可能导致自动驾驶决策危险延迟。

### 22. Revisiting Backdoor Attacks against Large Vision-Language Models from Domain Shift
- **发表场所**: arXiv 2024
- **年份**: 2024
- **大类**: 多模态后门攻击
- **链接**: https://arxiv.org/abs/2406.18844
- **总结**: 首次探索LVLM指令调整中跨域后门攻击，提出多模态归因后门攻击MABA。通过归因解释将域无关触发器注入关键区域，在视觉和文本域转移下评估攻击鲁棒性，攻击成功率比单模态攻击高36.4%。

### 23. Composite Backdoor Attacks Against Large Language Models
- **发表场所**: arXiv 2023
- **年份**: 2023
- **大类**: LLM后门攻击
- **链接**: https://arxiv.org/abs/2310.07676
- **总结**: 提出复合后门攻击CBA，将多个触发钥匙分散在不同提示组件中，比在同一组件中植入相同多个触发钥匙更隐蔽。只有当所有触发钥匙都出现时才激活后门，在LLaMA-7B上以3%污染样本达到100%攻击成功率。

### 24. A Patch-based Cross-view Regularized Framework for Backdoor Defense in Multimodal Large Language Models
- **发表场所**: arXiv 2026
- **年份**: 2026
- **大类**: 多模态后门防御
- **链接**: https://arxiv.org/abs/2604.04488
- **总结**: 提出基于补丁增强和跨视图正则化的统一防御框架，同时从特征表示和输出分布级别约束模型对触发模式的异常行为。通过补丁级数据增强和跨视图输出差异正则化，利用后门响应对非语义扰动异常不变性，主动分离原始和扰动视图的输出分布。

### 25. Stealthy Unlearning Attack (SUA) for MLLMs
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 多模态遗忘攻击
- **链接**: https://arxiv.org/abs/2506.17265
- **总结**: 研究MLLM遗忘攻击问题，提出SUA框架学习通用噪声模式，当应用于输入图像时可触发模型揭示遗忘内容。为提高隐蔽性引入嵌入对齐损失，确保攻击在语义上不可察觉，实验表明可有效从MLLMs恢复遗忘信息。

---

## 五、RAG/知识库后门攻击 (RAG & Knowledge Base Backdoor)

### 26. AgentPoison: Red-teaming LLM Agents via Poisoning Memory or Knowledge Bases
- **发表场所**: arXiv 2024
- **年份**: 2024
- **大类**: RAG后门攻击
- **链接**: https://arxiv.org/abs/2407.12784
- **总结**: 首次提出针对基于RAG的LLM Agent的后门攻击，通过毒化长期记忆或RAG知识库发起攻击。将触发生成表述为约束优化问题，在嵌入空间中高概率确保触发指令激活恶意演示，在三种真实LLM Agent上平均攻击成功率超80%。

### 27. BadPromptFL: Backdoor Threat to Prompt-based Federated Learning in Multimodal Models
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 联邦学习后门攻击
- **链接**: https://arxiv.org/abs/2508.08040
- **总结**: 首个针对多模态对比模型中基于提示的联邦学习的后门攻击BadPromptFL。受损客户端联合优化本地后门触发器和提示嵌入，注入毒化提示到全局聚合过程，利用CLIP架构的上下文学习行为实现高攻击成功率。

### 28. Merge Hijacking: Backdoor Attacks to Model Merging of Large Language Models
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 模型合并后门攻击
- **链接**: https://arxiv.org/abs/2505.23561
- **总结**: 首个针对LLM模型合并的后门攻击，攻击者构建恶意上传模型并释放，受害者合并后模型继承后门同时保持任务效用。攻击对各种模型、合并算法和任务有效，对两种推理时防御和一种训练时防御具有鲁棒性。

---

## 六、音频/语音后门攻击与防御 (Audio Backdoor Attack & Defense)

### 29. PaddingBack: Breaking Speaker Recognition with Invisible Backdoor Attack
- **发表场所**: arXiv 2023
- **年份**: 2023
- **大类**: 语音后门攻击
- **链接**: https://arxiv.org/abs/2308.04179
- **总结**: 利用广泛使用的语音信号操作——填充来生成中毒样本，提出不可闻的后门攻击PaddingBack。不使用外部扰动作为触发器，而是利用填充操作，使毒化样本与干净样本难以区分，在保持良性准确性的同时达到显著攻击成功率。

### 30. Enrollment-Stage Backdoor Attacks on Speaker Recognition Systems via Adversarial Ultrasound
- **发表场所**: arXiv 2023
- **年份**: 2023
- **大类**: 语音后门攻击
- **链接**: https://arxiv.org/abs/2306.16022
- **总结**: 提出Tuner攻击，在SRS注册阶段通过对抗超声波调制注入后门，不可闻、同步无关、内容无关且黑盒。利用随机语音内容、口语时间和音量增强优化过程生成超声后门，在七种SRS模型上成功验证。

### 31. Imperceptible Rhythm Backdoor Attacks: Exploring Rhythm Transformation for Embedding Undetectable Vulnerabilities on Speech Recognition
- **发表场所**: arXiv 2024
- **年份**: 2024
- **大类**: 语音后门攻击
- **链接**: https://arxiv.org/abs/2406.10932
- **总结**: 提出随机频谱节奏变换算法生成隐蔽毒化语音，从节奏成分变换角度设计触发器，保持音色和内容不变以提高隐蔽性，实验证明方法有效且隐蔽，需低污染率获得极高攻击成功率。

### 32. SPBA: Utilizing Speech Large Language Model for Backdoor Attacks on Speech Classification Models
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 语音后门攻击
- **链接**: https://arxiv.org/abs/2506.08346
- **总结**: 利用语音大语言模型生成多样化触发器，提出SPBA攻击方法。通过多梯度下降算法MGDA解决触发器数量增加导致的毒化率升高问题，在两个语音分类任务上验证了显著触发器有效性和攻击性能。

### 33. Backdoor Attacks against Voice Recognition Systems: A Survey
- **发表场所**: ACM Computing Survey 2023
- **年份**: 2023
- **大类**: 语音后门攻击综述
- **链接**: https://arxiv.org/abs/2307.13643
- **总结**: 对语音识别系统后门攻击进行综合综述，介绍VRS和后门攻击基础知识，从不同角度提出攻击分类，综合回顾现有攻击方法并分析优缺点，回顾经典后门防御方法和通用音频防御技术，讨论开放问题和未来方向。

---

## 七、通用后门防御技术 (General Backdoor Defense)

### 34. REFINE: Inversion-Free Backdoor Defense via Model Reprogramming
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 后门防御
- **链接**: https://arxiv.org/abs/2502.18508
- **总结**: 提出基于模型重编程的免反转后门防御方法REFINE，包括破坏后门模式的输入转换模块和重新定义模型输出域的输出重映射模块，通过监督对比损失增强防御能力同时保持模型效用，对各种自适应攻击具有抵抗性。

### 35. SEEP: Training Dynamics Grounds Latent Representation Search for Mitigating Backdoor Poisoning Attacks
- **发表场所**: TACL 2024
- **年份**: 2024
- **大类**: 后门防御
- **链接**: https://arxiv.org/abs/2405.11575
- **总结**: 利用训练动态识别高精度的毒化样本，随后通过标签传播提高召回率，提出SEEP防御方法。比现有先进防御方法显著降低多种后门攻击成功率，同时在干净测试集上保持高分类准确率。

### 36. CNPD: Class-Conditional Neural Polarizer for Backdoor Defense
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 后门防御
- **链接**: https://arxiv.org/abs/2502.18520
- **总结**: 受光学偏振器概念启发，提出轻量级后门防御方法NPD，在受损模型中集成神经偏振器作为中间层，实现为轻量级线性变换，通过双层优化学习，过滤毒化样本触发信息同时保留良性内容。

### 37. TED-LaST: Towards Robust Backdoor Defense Against Adaptive Attacks
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 后门防御
- **链接**: https://arxiv.org/abs/2506.10722
- **总结**: 增强TED对自适应攻击的鲁棒性，提出TED-LaST防御策略。引入标签监督动态跟踪和自适应层强调，在拓扑空间中不可分离和微妙拓扑扰动情况下识别威胁，在多种数据集和模型架构上有效对抗Sophisticated后门。

### 38. MADE: Graph Backdoor Defense with Masked Unlearning
- **发表场所**: arXiv 2024
- **年份**: 2024
- **大类**: 图神经网络后门防御
- **链接**: https://arxiv.org/abs/2411.18648
- **总结**: 首个图神经网络后门防御方法，提出对抗掩码生成机制选择性地保留干净子图，利用边缘权重掩码有效消除触发器影响，在各种图分类任务上显著降低攻击成功率同时保持高分类准确性。

### 39. BeniFul: Backdoor Defense via Middle Feature Analysis
- **发表场所**: arXiv 2024
- **年份**: 2024
- **大类**: 后门防御
- **链接**: httpshttps://arxiv.org/abs/2410.14723
- **总结**: 使用DNN中间层特征分析后门样本与良性样本的差异，提出后门一致性概念。设计由灰盒后门输入检测和白盒后门消除两部分组成的BeniFul方法，实现有效的后门输入检测和消除。

### 40. UNICORN: A Unified Backdoor Trigger Inversion Framework
- **发表场所**: arXiv 2023
- **年份**: 2023
- **大类**: 后门触发器反转
- **链接**: https://arxiv.org/abs/2304.02786
- **总结**: 提出统一的后门触发器反转框架UNICORN，能够在不同类型的神经网络和后门攻击中通用，通过学习触发器的分布特征来实现高效的后门检测和消除。

### 41. Eliminating Backdoors in Neural Code Models via Trigger Inversion
- **发表场所**: arXiv 2024
- **年份**: 2024
- **大类**: 代码模型后门消除
- **链接**: https://arxiv.org/abs/2408.04683
- **总结**: 针对神经代码模型的后门消除方法，通过触发器反转技术识别并消除代码模型中植入的后门，提出针对代码任务的专门后门检测和修复策略。

---

## 八、Prompt注入攻击与防御 (Prompt Injection Attack & Defense)

### 42. MELON: Provable Defense Against Indirect Prompt Injection Attacks in AI Agents
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 提示注入防御
- **链接**: https://arxiv.org/abs/2502.05174
- **总结**: 提出MELON防御方法，通过掩码重执行和工具比较检测攻击。设计攻击检测机制识别原始执行和掩码执行之间的相似性，在AgentDojo基准上优于现有防御，同时保持效用。

### 43. IPIGuard: Tool Dependency Graph-Based Defense Against Indirect Prompt Injection in LLM Agents
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: LLM Agent安全
- **链接**: https://arxiv.org/abs/2508.15310
- **总结**: 通过将Agent任务执行过程建模为工具依赖图遍历，提出IPIGuard防御范式。明确将动作规划与外部数据交互解耦，显著减少由注入指令触发的意外工具调用，增强对IPI攻击的鲁棒性。

### 44. ToolHijacker: Prompt Injection Attack to Tool Selection in LLM Agents
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: LLM Agent攻击
- **链接**: https://arxiv.org/abs/2504.19793
- **总结**: 首个针对LLM Agent工具选择环节的提示注入攻击，将恶意工具文档注入工具库操纵LLM Agent工具选择过程，强制为攻击者选择恶意工具用于目标任务，评估显示各种防御方法不足。

### 45. Signed-Prompt: A New Approach to Prevent Prompt Injection Attacks Against LLM-Integrated Applications
- **发表场所**: arXiv 2024
- **年份**: 2024
- **大类**: 提示注入防御
- **链接**: https://arxiv.org/abs/2401.07612
- **总结**: 提出通过签名提示方法保护LLM集成应用免受提示注入攻击，授权用户在命令段中签名敏感指令，使LLM能够辨别可信指令源，通过提示工程和微调两种方式实现。

### 46. Defense against Prompt Injection Attacks via Mixture of Encodings
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 提示注入防御
- **链接**: https://arxiv.org/abs/2504.07467
- **总结**: 提出编码混合防御方法，利用多种字符编码包括Base64来防御提示注入攻击，在保持所有NLP任务高性能的同时实现最低攻击成功率之一。

### 47. Defense Against Prompt Injection Attack by Leveraging Attack Techniques
- **发表场所**: arXiv 2024
- **年份**: 2024
- **大类**: 提示注入防御
- **链接**: https://arxiv.org/abs/2411.00459
- **总结**: 创新性地反转提示注入方法的意图，利用先前训练无关攻击方法开发新型防御方法，通过重复攻击过程但使用原始输入指令而非注入指令，实验证明优于现有训练无关防御方法。

### 48. To Protect the LLM Agent Against the Prompt Injection Attack with Polymorphic Prompt
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 提示注入防御
- **链接**: https://arxiv.org/abs/2506.05739
- **总结**: 提出多态提示组装PPA保护LLM Agent，通过动态变化系统提示结构防止攻击者预测提示结构，在接近零开销的情况下增强安全性同时不损害性能。

---

## 九、代码/其他后门攻击 (Code & Other Backdoor Attacks)

### 49. CodeBreaker: LLM-Assisted Backdoor Attack on Code Completion Models
- **发表场所**: arXiv 2024
- **年份**: 2024
- **大类**: 代码模型后门攻击
- **链接**: https://arxiv.org/abs/2406.06822
- **总结**: 利用LLM（如GPT-4）进行复杂payload转换，确保毒化数据和生成代码能逃避强漏洞检测。首个在代码补全模型上提供广泛漏洞集的框架，通过将恶意payload直接嵌入源代码实现攻击。

### 50. Exploring Backdoor Attack and Defense for LLM-empowered Recommendations
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 推荐系统后门攻击
- **链接**: https://arxiv.org/abs/2504.11182
- **总结**: 提出BadRec攻击框架，扰动项目标题并利用假用户与这些项目交互，毒化训练集并注入后门，仅1%污染数据即可成功植入后门。提出P-Scanner通用防御策略，利用LLM检测毒化项目。

### 51. AutoBackdoor: Automating Backdoor Attacks via LLM Agents
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: 自动化后门攻击
- **链接**: https://arxiv.org/abs/2511.16709
- **总结**: 首个通过LLM Agent自动化后门注入的通用框架，包括触发器生成、毒化数据构建和模型微调。利用强大语言模型Agent生成语义连贯、上下文感知的触发短语，在开源和商业模型上实现超90%攻击成功率。

### 52. The Trigger in the Haystack: Extracting and Reconstructing LLM Backdoor Triggers
- **发表场所**: arXiv 2026
- **年份**: 2026
- **大类**: 后门触发器提取
- **链接**: https://arxiv.org/abs/2602.03085
- **总结**: 提出从后门模型中提取触发器的实用扫描方法，利用后门样本往往记忆中毒数据的特点，通过记忆提取技术泄露后门示例，同时利用输出分布和注意力头的独特模式识别后门激活。

---

## 十、综合综述 (Comprehensive Surveys)

### 53. Threats and Defenses for Large Language Models: A Survey
- **发表场所**: ACM Computing 2025
- **年份**: 2025
- **大类**: LLM安全综述
- **链接**: https://doi.org/10.1145/3773365.3773631
- **总结**: 系统综述LLM在训练和推理阶段面临的安全威胁及对策。训练阶段包括数据投毒和后门攻击，推理阶段包括越狱和提示注入攻击，以及模型提取攻击。提出离线/在线防御策略分类，涵盖数据预处理、对抗训练、安全对齐和提示筛选。

### 54. Jailbreaking and Mitigation of Vulnerabilities in Large Language Models
- **发表场所**: arXiv 2024
- **年份**: 2024
- **大类**: LLM安全综述
- **链接**: https://arxiv.org/abs/2410.15236
- **总结**: 综合分析LLM面临的各种攻击方法和防御策略，涵盖基于提示的、基于模型的、多模态的和多语言的攻击，以及提示过滤、转换、对齐技术、多Agent防御和自regulation等防御机制。

### 55. SoK: a Comprehensive Causality Analysis Framework for Large Language Model Security
- **发表场所**: arXiv 2025
- **年份**: 2025
- **大类**: LLM安全因果分析
- **链接**: https://arxiv.org/abs/2512.04841
- **总结**: 提出统一因果分析框架，支持从标记级、神经元级、层级到表示级干预的各级因果调查。首次综合调查因果驱动的越狱研究，在多种安全关键基准上验证，发现安全相关机制高度局部化，因果特征提取在多种威胁类型上实现超95%检测准确率。

### 56. Mind the Agent: A Comprehensive Survey on Large Language Model-Based Agent Safety
- **发表场所**: OpenReview 2024
- **年份**: 2024
- **大类**: LLM Agent安全综述
- **链接**: https://openreview.net/pdf?id=DHe0UXipKU
- **总结**: 针对LLM Agent安全性的综合综述，分析LLM Agent在安全关键应用中的潜在威胁和防御策略。

---

## 论文分类索引

### 按研究阶段分类

| 阶段 | 论文编号 |
|------|----------|
| **训练前-数据投毒检测** | 35, 53 |
| **训练后-离线后门扫描** | 1, 10, 34, 40, 41, 52 |
| **推理时-动态后门检测/防御** | 2, 3, 6, 7, 8, 9, 11, 24, 34, 36, 37, 42, 43, 47, 48 |

### 按攻击向量分类

| 攻击向量 | 论文编号 |
|----------|----------|
| **数据投毒** | 22, 23, 25, 27, 49, 50, 51 |
| **权重篡改** | 3, 4, 14, 28, 52 |
| **RAG/知识库污染** | 26, 27 |
| **语音/音频触发** | 12, 13, 29, 30, 31, 32, 33 |
| **多模态触发** | 14-25 |
| **提示注入** | 42-48 |

### 按模态分类

| 模态 | 论文编号 |
|------|----------|
| **文本LLM** | 1, 2, 5, 9, 23, 34, 35, 36, 37, 42-48, 49, 51, 53-55 |
| **多模态（视觉+语言）** | 6, 7, 14-22, 24, 25, 39, 40 |
| **语音/音频** | 10, 12, 13, 29-33 |
| **代码** | 41, 49 |
| **图神经网络** | 38 |
| **推荐系统** | 50 |

---

*文档生成时间：2026-04-13*
*搜索来源：Semantic Scholar*
*筛选标准：安全四大 > 人工智能/计算机顶会 > 安全顶刊 > 人工智能/计算机顶刊 > arXiv*
