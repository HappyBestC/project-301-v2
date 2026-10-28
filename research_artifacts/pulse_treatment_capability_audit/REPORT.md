# Pulse 治疗能力边界与原生验证报告

审计日期：2026-10-19（Asia/Shanghai）。范围：301 服务器现有 Pulse，人类成人全身模型；技术能力验证，不改业务代码。以下“有效”仅指本次仿真出现可归因的输出变化，不代表现实疗效或临床准确性。

## 执行摘要：四个核心问题

1. **治疗指令粒度**：实际版本确认为 **4.3.2**。最小控制单元是一个具体 `SEAction` 的参数化实例及其内部槽位键（动作类型、侧别、物质名、复合物名或出血 compartment）。连续参数使用 double 和物理单位；当前 Soldier 状态时间步 **0.02 s**。没有统一的“治疗动作等级”，也没有通用伤口坐标、器械型号、操作者技能或操作成功率参数。敷料、减压只到左右侧开关；输注可到浓度、体积速率和剩余体积。
2. **药物与精确剂量**：原生支持具体物质、推注和输注；推注 `Dose` 是**体积**，质量须由浓度×体积计算。当前文件有43种单物质、4种复合物，19种有PD数据块，但不等于19种完整临床药效。Prednisone的PD效应项全为0。肾上腺素1.25与5 μg产生不同浓度及生理响应，Morphine 1 mg出现镇静及呼吸/心率变化（S4）。
3. **多动作同时**：允许同一仿真时刻串行提交后统一推进；不同槽位可以保留。盐水与氧疗持续重叠并独立停止已确认（S3）；肾上腺素+盐水的四组对照证明共同影响（S4）。这不等于允许同一引擎多线程调用。
4. **冲突**：同键动作通常覆盖，不累加；同药未完成推注覆盖会重置给药进度。呼吸设备互斥可能延迟至推进时才失败。批次不原子：一项失败，其他项仍可能已执行。Pulse只做部分结构、物理状态和设备检查；适应证、禁忌证、剂量策略、药物交互风险、资源及幂等性需要Agent处理。

## Pulse 版本与本地运行环境

- 源码：`/home/private/project-301/engine-stable`。`CMakeLists.txt:46`：`project(Pulse VERSION 4.3.2 ...)`。
- 本次直接加载：`/home/private/project-301/pulse/bin/PyPulse.cpython-311-x86_64-linux-gnu.so`，运行时 `PyPulse.__version__ == '4.3.2'`。SHA256：`f7eeb22ccef5392b2c0e2698037bc0aa47b0bf595f959c4c8dbc94f5d48023cf`。
- 使用原有 `.venv-pulse`、`activate-pulse.sh` 和安装包 `pulse/python`，没有重新编译Pulse。C++ SDK位于原安装的`include/`、`lib/`；源码示例位于`src/cpp/howto`，Python示例位于`pulse/python/pulse/howto`。本次通过既有pybind扩展直接执行C++引擎，不依赖301生产封装。
- v2的`pulse`指向`/home/private/pulse-4.3.2-301-runtime`，安装manifest的扩展哈希与本次一致，但精简包只带StandardMale状态。为满足Soldier优先要求，使用原安装数据目录。
- 患者：`pulse/bin/states/Soldier@0s.json`，SHA256 `a3febbc7a2281f46a745521f524bc79503e1c022271d703140f802ecdf5e8100`。原生初始患者返回Name=Soldier、22岁、体重约77.11 kg；Sex使用protobuf默认Male（零值在JSON中省略），没有使用女性模型。
- 每个实验新建独立引擎、从同一状态文件加载，初始t=0，dt=0.02 s。未重用上一实验末态；胸伤/出血治疗组与其伤情对照采用相同伤情输入及治疗前时程。
- `environment.json`保存运行包与患者身份，`source_hashes.json`固定关键源文件；`SOURCE_EVIDENCE.md`保存带原始行号的调用链摘录。版本和扩展一致性已核实，但没有重构建证明每一源码字节都对应二进制：S1与原生结论仍分别标记。

## 证据分级与交付物解释

- S1：本地定义及实现；S2：底层接口真实接受/拒绝；S3：推进及状态生命周期；S4：同初态对照观察到生理影响。不能跳级。
- **尚未验证**：有API/模型，但没有本次原生覆盖；**证据不足**：如完整临床药物交互准确性没有依据；**当前版本不支持**：如直接止血带Action、骨内推注执行路径；**测试受阻**：具体实验无法推进，例如不兼容气道组合（这本身是冲突证据，不是所有实验受阻）。
- `action_inventory.csv`共72行：65个源码数据结构/动作项（含伤情、评估、设备故障和1个模式基类，**不是65种治疗**），另7行现实措施能力缺口。范围包含全部PatientAction、治疗相关Environment及设备Action。`SEMechanicalVentilatorMode`是嵌套基类，不能单独提交。
- `parameters`展开protobuf嵌套配置、字段类型、枚举、oneof和已定义单位；`required_validation`、`active_validation`保留真实C++逻辑，而不是把proto3字段误当作必填字段。`action_parameter_details.json`便于机器检索；`scalar_units.json`是本地单位清单。
- JSON中的Comment是元数据；`TotalBloodLost`、`TotalBloodVolume`、`TotalInfusedDose`是引擎运行状态，不建议Agent填写。配置对象的字段存在不等于设置任何值都合法，需结合ToSettings、模型路径及本表验证等级。

## 治疗 Action 能力分析

下表给出救助相关主干；完整字段及枚举以CSV为准。类名前缀均为`SE`。Python高级接口存在时用同名类（如`pulse.cdm.patient_actions.SESubstanceBolus`）；通用入口为`PyPulse.Engine.process_actions(ActionListData的JSON, PyPulse.serialization_format.json)`。

| 治疗 | 原生类 | 参数/最细粒度 | 生命周期、停止与证据 |
|---|---|---|---|
| 出血控制 | `SEHemorrhage`（间接） | Compartment必填；Severity[0,1]或FlowRate；Type内/外出血；同compartment槽位，Severity优先 | 降低/置零改变出血源，不是止血器材仿真；S1/S2/S3/S4，hemorrhage_stop |
| 止血带、压迫、填塞 | **无直接Action** | 无压力、宽度、位置、缺血计时等原生参数 | 可映射减少出血；不能声称再现止血带并发症 |
| 胸腔封闭敷料 | `SEChestOcclusiveDressing` | Side=Left/Right必填，State=On/Off；不支持敷料面积/密封率 | 同侧覆盖、Off移除；需要同侧气胸，否则下一步报错移除；chest_dressing S4 |
| 针刺减压 | `SENeedleDecompression` | Side、State；没有针径/深度/精确肋间坐标参数 | 固定模型阻力通路；同侧Off停；probe_needle S3，效果未验证 |
| 胸管引流 | `SETubeThoracostomy` | Side必填；FlowRate在schema注为optional，但IsActive实际要求存在 | 模型上限1 mL/s；无FlowRate可被接受却不活跃；probe_tube S3；零流量不等于删除，未验证引流疗效 |
| 气道管理 | `SEIntubation` | Type=Off/Esophageal/LeftMainstem/RightMainstem/Tracheal/Oropharyngeal/Nasopharyngeal；可选AirwayResistance、Severity | 单Type槽位，覆盖旧类型，Off停；probe_intubation S3；并非多根气道器材同时存在 |
| 氧疗 | `SESupplementalOxygen` | Device=None/NasalCannula/SimpleMask/NonRebreatherMask，Flow、Volume；非所有字段在IsValid强制 | 持续消耗氧气，Device=None停；设备缺参数有默认处理；overlap S3 |
| 通用通气 | `SEMechanicalVentilation` | State；On时Pressure或Flow至少一个；GasFraction总和1且为气体；Aerosol固/液浓度 | 压力/流量持续，Off停；可由上层逐步更新波形；probe_mv S3，非完整呼吸机控制器 |
| 呼吸机 | `SEMechanicalVentilatorConfiguration`及CPAP/PressureControl/VolumeControl/Hold | FiO2、PEEP、压力/容积、频率、吸气时长、触发与切换阈值、波形等；Settings/File、MergeType | 配置存入设备；模式互相替换，连接Off断开；S1，本次未原生验证具体呼吸机模式 |
| 简易呼吸囊 | `SEBagValveMaskConfiguration/Automated/Squeeze/Instantaneous` | 配置Connection；频率、I:E、挤压压力或容积、吸呼时长，或即时压力/流量 | Squeeze单周期；Automated持续；Instantaneous保持至更新；不同控制模式互相移除；BVM自动模式短程S3 |
| 药物推注 | `SESubstanceBolus` | Substance、Dose体积、Concentration必需；Route，AdministrationDuration可选 | 默认2s，完成移除；同药覆盖进度；详见药物节，S4 |
| 单物质输注 | `SESubstanceInfusion` | Substance、Rate、Concentration必需；Volume可选 | 每步注入，缺Volume默认1000mL；Rate=0停止，袋耗尽结束；S3 |
| 复合输液/输血 | `SESubstanceCompoundInfusion` | SubstanceCompound、BagVolume、Rate必需；Blood/PackedRBC/Saline/Sweat来自数据文件 | 按复合物名覆盖；Rate=0或袋空停；Saline S4，Blood短程S3，PackedRBC未验证；Sweat存在不代表适合治疗 |
| 心肺复苏 | `SEChestCompression/Automated/Instantaneous` | Force(N)或Depth(m/cm等)；单次需要CompressionPeriod；自动有CompressionFrequency、AppliedForceFraction | 按压类型互相替换；单次完成/强度归零/替换；S1，未进行心脏骤停疗效实验 |
| 吸入器给药 | `SEInhalerConfiguration` + `SEConsciousRespiration`内`SEUseInhaler` | 物质、计量剂量、喷嘴损失、间隔器体积；UseInhaler子命令触发一次 | 配置不是一次给药；S1，当前安装无同名高级Python吸入器配置类，可走JSON；未原生验证 |
| 麻醉机 | `SEAnesthesiaMachineConfiguration` | 连接、供氧源、呼吸参数、左右药室物质/浓度、氧瓶等嵌套配置 | 设备状态与气道模式；JSON/C++有定义，高级Python类缺失；S1未验证 |
| ECMO | `SEECMOConfiguration` | 引流/回输部位枚举、氧合器体积、TransfusionFlow、复合物和逐物质浓度 | 配置式支持；S1未验证，不能将字段存在等同完整ECMO临床模型 |
| 保温/降温 | `SEThermalApplication`、`SEChangeEnvironmentalConditions` | 加热/冷却功率、面积/面积比例、施加温度及环境温湿度等 | AppendToPrevious可追加或替换，环境配置有MergeType；S1未验证；无精确解剖部位 |
| 营养补水 | `SEConsumeNutrients` | Nutrition或NutritionFile；糖脂蛋白、电解质、水及消化速率 | 通过胃肠模型消费；不是任意口服药物吸收接口；S1未验证 |
| 参数干预 | 呼吸/心血管MechanicsConfiguration/Modification | Settings或Modifiers及文件；MergeType、AppliedCycle或Incremental | 间接建模，不是现实操作。非Incremental修改可触发重新稳态，不能纳入普通“零时间提交”假设 |

**没有统一撤销**：Off/None、零值、耗尽、有限周期完成、配置替换分别适用；停止给药不撤回已经进入体内的药物，停止失血不补回已失血量。状态保存/恢复是实验分支手段，不是现实治疗逆转。

**源代码边界**：`SEPatientActionCollection.cpp:193`以后按类型识别、复制和激活；`:438`出血按compartment；`:361`敷料按侧；`:481`气道单槽；`:584`各物质槽位。`RespiratoryModel.cpp:1730`敷料和针刺作用到不同胸腔阻力通路；`:1805`以后检测缺少适应伤情并移除。`:1870`以后胸管是血胸流出模型，不应把它的类名扩张成全部临床胸腔引流能力。

## 药物及剂量控制能力分析

### 实际数据与模型范围

`SESubstanceManager::LoadSubstanceDirectory`（`src/cpp/cdm/substance/SESubstanceManager.cpp:271`）读取运行数据目录`substances/*.json`及`substances/compounds/*.json`。本地43个物质中19个带PD：Albuterol、Desflurane、Epinephrine、Etomidate、Fentanyl、Furosemide、Ketamine、Lorazepam、Midazolam、Morphine、Naloxone、Norepinephrine、Oversedation、Phenylephrine、Pralidoxime、Prednisone、Propofol、Rocuronium、Succinylcholine。Oversedation是人为效果物质名，不是现实药品。

其余24项为Acetoacetate、Albumin、Bicarbonate、Calcium、Carbaminohemoglobin、CarbonDioxide、CarbonMonoxide、Carboxyhemoglobin、Chloride、Creatinine、ForestFireParticulate、Globulin、Glucose、Hemoglobin、Insulin、Lactate、Nitrogen、OxyCarbaminohemoglobin、Oxygen、Oxyhemoglobin、Potassium、Sodium、Tristearin、Urea。它们不是24种“无效药”：氧气、CO、胰岛素、葡萄糖等存在专用生理/代谢路径，但不能套用通用PD疗效保证。Insulin相关计算可见`TissueModel.cpp:747,966,1127`。

特别发现：**Prednisone虽有PD块，所有效应modifier均为零**；本次源码搜索未见专门抗炎作用逻辑，不能宣称其治疗炎症有效。Naloxone用通用正呼吸、负镇静modifier表达，未见阿片受体竞争拮抗模型。没有TXA药物文件，也没有原生止血带或抗生素感染治疗Action。本地增加一个药名/文件并不自动获得正确药效。

`DrugModel.cpp:145`在PreProcess施加三类给药；`:162`计算分配、清除、血浆浓度，PD开关启用才计算药效；`:515`遍历有PD的液体物质，使用浓度/EC50的Emax-Hill关系，将HR、血压、呼吸、镇静、神经肌肉阻滞、支气管扩张等modifier相加，并对部分总效应限幅。PK/清除字段是否存在逐药记录于CSV。数据完整、模型科学有效、特定适应证有效是三件不同的事。

### 给药方式、量纲和生命周期

| 方式 | 真正接口 | 输入与执行边界 |
|---|---|---|
| IV/IA/IM推注 | `SESubstanceBolus`；Python `set_substance/set_admin_route/get_dose/get_concentration/get_admin_duration` | `DrugModel.cpp:225`switch只实现Intravenous、Intraarterial、Intramuscular；IV有S4，IA/IM仅1秒S3，不证明吸收曲线准确 |
| 其他枚举途径 | 同接口内的Epidural/Intraosseous/Intracardiac等枚举 | enum可解析不等于支持；Intraosseous实测S2接受、下一步记录Unavailable并移除，60s与基线输出相同 |
| 连续IV输注 | `SESubstanceInfusion`；`set_substance/get_rate/get_concentration/get_volume` | 无独立Route；每步给入vena cava；可变速、停输；不同药名可共存 |
| 复合液IV | `SESubstanceCompoundInfusion`；`set_compound/get_rate/get_bag_volume` | 组分由文件定义，Saline补充血容量已确认；单物质给药实现仍有“添加液体体积”TODO，不能代替晶体液复合物接口 |
| 重复给药 | 完成后再提交同药Bolus | repeat_completed在0、10s提交，两次均接受并执行；未完成时同药没有队列，覆盖原参数及TotalInfusedDose |
| 修改/停止 | 同键完整action覆盖；Rate=0停止输注 | infusion_update_stop在0/10/20/40s依次1/1/2/0 mL/min；重复输入Volume=10会重置袋余量，非仅修改速率的patch |
| 联合药物 | 多个不同Substance槽位 | Epinephrine+Morphine两药共同变化S4；药效相加/生理反馈不等于完整DDI |

量纲必须分开：

- 推注目标质量 `mass = concentration × volume`。本次Dose=1mL；Concentration=1.25或5 μg/mL，得到1.25或5 μg。Morphine为1000 μg/mL×1mL=1mg。
- 输注质量速率 `mass_rate = concentration × volume_rate`；总质量由积分时间及剩余体积限制。这里Rate是mL/min而不是μg/min。
- 推注支持AdministrationDuration，省略默认2s；单物质输注支持Volume，未提供默认1000mL；复合输液支持BagVolume。通用持续时间由Agent安排停止，不能假定每个Action都有duration。
- 示例单位：体积L/mL/μL对应引擎字符串`L/mL/uL`；浓度`g/L, g/mL, mg/mL, mg/L, ug/mL, ug/L`等；速率`L/s, L/min, mL/s, mL/min, mL/hr`等；时间`s/min/hr`等。完整可用拼写见`scalar_units.json`，不得自行生成未识别单位。
- C++ double、protobuf double、Python float支持小数；实测1.25输入原样保存在动作状态中。不存在经验证的“无限精度/最小μg刻度”。数值表示精度不等于剂量执行或药效精度；0.02s离散化、近零判定、袋末步和模型近似都有限制。
- IsValid一般检查参数存在/标量有效，**没有完整的临床剂量上下限**。`SEScalar0To1.cpp:12`检查[0,1]；普通带单位double不能据此推定非负和有限值全部已检查。负输注质量在DrugModel中可能Fatal，Agent必须先检验有限、非负、时长>0及量纲。
- `DrugModel.cpp:338`附近复合输注将mL/s变量与285比较，错误文字却写285 mL/min：单位语义不一致。此处仅S1，没有进行危险边界实验，不能引用错误文字作为可靠限速。
- 推注没有末步min截断，有限输注袋末步有纠正剩余剂量TODO；非整步时长/袋尾的准确总量未验证。“精确指定目标参数”已支持，“所有边界下严格质量守恒给完目标量”证据不足。

### 药效与组合对照（S4）

每组相同Soldier状态，0s提交，推注2s；盐水250mL袋、60mL/min，观察60s。下表为实际t≈10s，四舍五入；全采样值见`physiology_comparison.csv`。

| 组别 | HR /min | MAP mmHg | SBP mmHg | 血容量 mL | Epinephrine μg/mL | 镇静水平 |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 84.0268 | 94.8048 | 114.4750 | 5488.8253 | 0.000060 | 0 |
| Epi 1.25 μg | 84.0297 | 94.8064 | 114.4768 | 5488.8253 | 0.000286 | 0 |
| Epi 5 μg（A） | 97.6140 | 100.8797 | 133.6764 | 5488.7405 | 0.000959 | 0 |
| Saline（B） | 83.9894 | 94.8941 | 114.6071 | 5498.8246 | 0.000060 | 0 |
| A+B | 97.6084 | 101.1976 | 134.0949 | 5498.7400 | 0.000957 | 0 |
| Morphine 1mg | 79.1565 | 89.0014 | 108.7041 | 5488.8977 | 0.000060 | 0.207553 |
| Epi 5μg + Morphine 1mg | 93.1217 | 96.0439 | 129.5571 | 5488.8008 | 0.000965 | 0.207493 |

低剂量Epi在本状态的生命体征效应很弱，不能把约0.003/min差值描述成强疗效；高剂量相对基线HR约+13.59/min，且浓度、血压均改变，支持本模型剂量响应，非线性明显（此药Hill shape=10）。Morphine 60s呼吸频率约12.40/min、镇静0.19145；未验证疼痛，因为本次没有相应疼痛终点。正常Soldier改善或偏移生理值也不等于创伤患者获益。

组合同时保留两个动作，推进后药物浓度及盐水剩余袋量变化，且A+B相对A增加血容量、相对B增加心率/血压。60s盐水组血容量5550.7687mL，基线5490.7904mL，差约59.98mL。AB与BA所有共同采样有限数值完全相同（`comparison_checks.json`）。未把此一组合的顺序无关性推广到其他组合。

## 多动作同时施加机制分析

**A：同一仿真时刻提交。** `PhysiologyEngineThunk.cpp:268`将ActionList反序列化后，按顺序调用每个`ProcessAction`；普通治疗不在这里推进时间。`combo_high_AB/submit_0_0.json`、`submit_0_1.json`均t=0，第二份同时包含Bolus和CompoundInfusion；然后第一次推进到0.02s。C++动作被复制，调用者之后修改Python对象不会自动改变引擎，须再次提交。批次是顺序循环，不是并行、原子事务或“先全部检查后全部生效”。

**例外**：`AdvanceTime`动作本身会推进；MechanicsModification默认可触发稳定化（`Controller.cpp:828`以后）。因此301接口只应将已审计的普通治疗列入零时间提交集合，不能对所有SEAction泛化。

**B：持续动作重叠。** overlap中盐水0s开启，氧疗20s开启，40s关闭氧疗，60s结束；20–40s快照有两项持续动作，40s之后保留盐水，袋量继续下降。氧疗停止不会撤销输液。输注状态更新测试重复提交后只有一项Epinephrine infusion：10s的重复设置不是增加第二条通路；20s速率变2；40s速率0后动作移除，体内药物仍继续清除。

**C：共同生理作用。** 前节四组对照提供S4证据；两种持续动作的状态共存与生理共同影响是分开的判断。给药过程中2s后Bolus从活动列表消失，药物依然在体内产生效应，所以“活动Action列表没有Bolus”不能解释为“药效已停止”。

**时间推进**：`Controller::AdvanceModelTime`（`:601`）按CheckIntubation→PreProcess→Process→PostProcess更新；成功后递增模型时间。设备、药物、呼吸/循环等通过共同生理状态耦合。动作提交顺序与内部模型计算顺序是两件事；本次气道AB/BA均先在呼吸模型处理通用机械通气、再处理氧疗时失败。

**线程边界**：本次全部单引擎串行执行。没有发现同一引擎可重入的保证，未做并发调用测试。可对不同患者使用独立进程/引擎；同一患者只能一个执行者串行操作。这是执行策略建议，不是已证明某种线程调度必然崩溃。

**Python重要陷阱（S1）**：安装版`pulse/python/pulse/engine/PulseEngine.py:206–219`的高级`process_action`/`process_actions`没有return底层bool，正常情况下返回None。不能把None当拒绝或无异常当成功。本次直接调用底层`PyPulse.Engine.process_actions`，捕获其bool；本扩展没有导出`pull_active_actions`，通过`serialize_to_string`的`ActiveActions`提取原生状态。设备配置消费后还应查询设备状态，不能只看ActiveActions；短程设备probe还用原生日志核对AirwayMode。

## 多动作冲突处理机制分析

| 场景 | 真实处理 | 证据/责任 |
|---|---|---|
| 同药同类型推注 | 同物质键Copy覆盖；不是追加队列 | S1 `SESubstanceBolus.cpp:41`没有保存TotalInfusedDose；S3 bolus_overwrite与epi_high轨迹完全一致 |
| 同药输注变速/重复 | 覆盖Rate/Concentration/Volume；没有同药多管路ID | S3 infusion_update_stop；Agent维护剩余量、避免无意重置袋量 |
| 不同药物 | 独立槽位共存；PD通用求和及限幅 | S4 multidrug_high；药物相互作用准确性证据不足 |
| Bolus+Infusion同药 | 不同动作类型保存到不同容器，源码可共存 | S1，未原生验证；应由Agent决定是否允许额外负荷 |
| 同侧敷料/减压 | 各自按左右侧保存；重复同侧同类覆盖 | S1；同侧两种不同干预的组合仅源码确认，未原生验证 |
| 同compartment多伤口 | Hemorrhage按compartment覆盖，不按伤口ID，也不把Type当独立键 | S1；Agent先汇总多个伤口出血源，避免互相覆盖 |
| 多气道类型 | Intubation单槽，后者替换前者 | S3 probe_intubation；不是两个气道器材真实共存 |
| O2+通用机械通气 | 两次提交true、两动作可保存，但首次advance返回false，时间仍0 | S2/S3 airway_AB/BA；日志“Can only change airway mode from the Free mode, Disable other equipment first.” |
| 呼吸机PC/VC/CPAP | 新模式移除其他模式，再ToSettings转换；转换仍可能失败 | S1 `SEEquipmentActionCollection.cpp:160–230`；未原生验证这些模式 |
| BVM的三种控制 | 新Automated/Squeeze/Instantaneous移除其他控制模式 | S1 `SEEquipmentActionCollection.cpp:250`以后；只测试单自动模式 |
| 多种胸外按压 | 新模式移除旧模式，部分有warning | S1 `SEPatientActionCollection.cpp:298–359`；未原生验证 |
| 无气胸就敷料/减压 | 可接受，但模型步检查后移除、记错误 | S3 dressing_without_injury，60s与基线一致；不能仅看提交true |
| 配置重复 | 部分使用MergeType；ThermalApplication可AppendToPrevious | S1；不能把“所有重复Action都全量覆盖”作为全局规则 |
| 一个批次有无效动作 | 整体false，不回滚之前动作，并可能继续处理后续动作 | batch_partial中Saline、缺Dose Bolus、O2：返回false但Saline/O2都保留，推进0.02s成功（S3） |

**相互作用模型**：源码确认的是多个物质效应modifier相加、部分阈值/限幅、及各生理系统反馈耦合；不是一般性的受体竞争、酶抑制/诱导、配伍沉淀、过敏、输血相容性或临床DDI引擎。镇静累计参与呼吸效应分支，说明一般情况下也不能推定严格线性可加或全面顺序无关。未进行药物清单中全部两两组合实验。

**内部责任**：已知字段合法性/枚举和单位转换；部分比例范围、气体组分总和；动作槽位覆盖/停用；部分适应伤情检查；设备AirwayMode互斥；模式替换；耗尽和时段结束；少量物理阈值。

**Agent责任**：给药质量换算、有限值/非负/速率/时长边界；适应证、禁忌证、药物特异交互和器材兼容策略；同伤口/同器材指令归并；患者、侧别、物质身份；库存、袋余量及已给入量；重复请求幂等；事件时刻对齐；提交失败/推进失败后的核对和故障状态；不把异常简单当死亡。不能自动重放返回false的批次，否则可能重复给药。上层校验不需要增加人工审批流程。

## 原生实验设计和验证结果

共 **33个独立短程场景**：32个常规case加1个批次部分失败probe。22个60s场景、8个1s probe、2个计划0.1s但首步失败的气道场景，另批次推进0.02s；串行执行，无大规模批处理。每场景有独立日志；全部共享同一个已哈希的Soldier初始文件。药物参数为模型技术探针，不是301临床剂量建议。

运行命令（运行前原始输出目录必须不存在；脚本使用exist_ok=False保护已有结果；复现实验请复制整个研究目录到新目录再运行，不要删除原证据）：

```bash
bash tests/run.sh
bash tests/run_additional.sh
bash tests/run_probes.sh
source /home/private/project-301/activate-pulse.sh
python tests/batch_probe.py
python tests/build_inventory.py
python tests/summarize.py
```

前三个shell脚本记录了本次绝对路径，复制复现时需将其中研究目录改为新路径；数据及源码根仍指向既有安装。`build_inventory.py`生成初始清单，`summarize.py`添加实验等级和能力注记，顺序不可反转。它们仅写研究目录。

每case记录：`events.json`中的实际提交前后时间、输入、底层bool、初始化信息、推进失败；`submit_*.json`和`advance_*.json`中的原生活动动作及时间；`samples.csv`中的生理指标和两药血浆浓度；`pulse.log`及stdout保留原始错误。常规60s每5s采样，提交后第一步补采样；probe短于5s时最终时间以events/final状态为准，CSV最后一行可能不是1s终点。初始未激活Morphine浓度NaN被原样保留，不伪装成0；第一次推进后由引擎输出0。

初版16个case的末尾`completed:true`只表示脚本走到收尾，**不表示advance成功**。气道两组events更早已记录`advance_failed_at_step:0`；`test_results.csv`据此明确标失败。后续脚本改为`loop_finished/reached_requested_end`区分。原始日志未被追改。

| 编号 | 实验映射 | 结论与等级 |
|---|---|---|
| T01 | saline；chest_control/chest_dressing；probe_mv等 | 原生治疗接受、执行；盐水血容量和敷料配对有S4。胸伤60sHR：90.0796→87.0843/min；SpO2：0.971935→0.972247，方向变化较小，不夸大疗效 |
| T02 | baseline/epi_low/epi_high | 1.25/5μg精确输入、浓度差异、HR/SBP剂量响应S4 |
| T03 | infusion_update_stop | 20s由1→2mL/min，仍仅一个槽位，S3 |
| T04 | 同上 | 40sRate=0，活动输注移除；已经注入的药物不消失，S3 |
| T05 | combo_high_AB/BA | t=0双动作提交，时间不变，两动作保存；S3 |
| T06 | overlap | 盐水持续时开启/关闭氧疗，独立保留和停止，S3 |
| T07 | infusion_update_stop；repeat_completed | 同值重复输注覆盖，Volume重置；已完成推注可以再次执行，S3 |
| T08 | bolus_overwrite；probe_intubation | 同刻1.25→5μg覆盖，输出与单独5μg一致；插管类型覆盖，S3；覆盖后的药效有S4 |
| T09 | airway_AB/BA | 提交接受、推进失败，有错误日志；不是兼容通过，S2/S3冲突证据 |
| T10 | morphine/epi_high/multidrug_high | 两药共同进入模型、镇静与循环指标共同变化，S4；不证明临床DDI准确性 |
| T11 | combo_high_AB/BA；airway_AB/BA | 本兼容组合换序结果相同；不兼容组合换序仍失败，不推广为全局顺序无关 |
| T12 | baseline/epi_high/saline/combo_high_AB | 四组析因对照，独立生理贡献可见，S4 |
| 补充 | unsupported_route | 骨内枚举接受后移除，输出与基线一致；执行路径当前不支持 |
| 补充 | invalid_missing_dose、batch_partial | 缺Dose返回false；批次无回滚、有效动作继续执行，S2/S3 |
| 补充 | hemorrhage_control/stop | 20s置零Severity，60s血容量5448.2570→5476.2139mL；间接出血控制S4，不是原生止血带 |
| 补充 | probe_IA/IM/needle/intubation/tube/blood/bvm/mv | 八组1s接口/生命周期探针，只支持S2/S3；未验证对应长期疗效 |

**失败未掩盖**：气道场景计划推进0.1s而实际0s；无效推注返回false；骨内给药与无伤情敷料提交成功但模型移除；这些在报告、矩阵、test_results和原始日志中分别记录。没有Mock、没有将未执行模式填为通过。

## Pulse 自身能力边界

**确认支持（依具体S等级）**：本地4.3.2；原生参数化治疗动作；小数浓度/体积/速率输入；IV药效与剂量响应；短程IA/IM执行；连续输注更新/停用；盐水容量作用；敷料对气胸模型作用；多动作同刻保存、持续重叠、共同生理影响；同槽覆盖、设备互斥错误及非事务批次行为。

**确认不支持的直接能力**：止血带/伤口填塞/骨折固定/手术缝合/电除颤独立Action；本DrugModel骨内等非IV/IA/IM推注途径；任意药名自动药效；同一药物同类型多独立输注管路；同compartment多独立Hemorrhage伤口；原子多动作提交与自动事务回滚。改变Arrhythmia或Hemorrhage不是实际电除颤/止血带物理模型。

**仅源码确认尚未原生验证**：PC/VC/CPAP、麻醉机、ECMO、吸入器、营养、温控、按压各模式、PackedRBC、绝大多数药物；同药Bolus+Infusion、左右侧全部组合、同侧针刺+敷料、复杂设备顺序切换。已有S3的一秒probe亦不升级为S4。

**主要限制**：单一正常男性状态、观察至60s；没有休克/重度呼吸衰竭全谱剂量验证、长期药代、过敏/感染、全药对相互作用、输血配型或生存终点验证。结果是确定性最小机制探针，未重复多随机种子，也没有统计显著性声明。S4只证明本模型当前参数下有响应，不证明现实准确。

## 救助 Agent 需要补充的能力：最小接口与调度方案

保留301既有业务逻辑，本报告只建议一个薄适配层。治疗指令应明确分离现实治疗意图与Pulse动作，并保留证据等级；对“止血带→减少Hemorrhage”必须标注间接映射，效果系数是Agent建模假设，不能伪装引擎原生事实。

建议最小指令结构：

```json
{
  "command_id": "unique-id",
  "patient_id": "Soldier-case-001",
  "expected_time_s": 20.0,
  "operation": "start|update|stop",
  "native_action": "SubstanceInfusion",
  "target": {"substance": "Epinephrine"},
  "parameters": {
    "concentration": {"value": 1.0, "unit": "ug/mL"},
    "volume_rate": {"value": 1.0, "unit": "mL/min"},
    "remaining_volume": {"value": 10.0, "unit": "mL"}
  },
  "schedule": {"stop_at_s": 40.0},
  "mapping": {"support": "native", "evidence": "S3"}
}
```

此例是接口结构示意而非治疗处方。推注另用`dose_volume`、`concentration`、`route`、`administration_duration`；业务若传目标质量，适配层计算体积并同时留存目标质量与转换结果，校验两者一致。部位动作使用side/compartment枚举；不能接受自由文本直接透传。`update`必须读取/维护当前状态并构建完整替换action，尤其保护剩余袋量和推注已给量；没有通用PATCH保证。

最小原生执行接口：`load_state`、`submit_one`、`advance_steps`、`read_observations`、`read_execution_state`、`close`。回执至少含`accepted`、`simulation_time_before/after`、`advance_ok`、`active_state`、`error/events`；S4效果应作为另行分析字段，不能从accepted推导。

执行顺序：

1. 按患者串行排队，将事件对齐dt；核对患者、期望时间、单位、范围、途径白名单、槽位键及设备互斥。
2. 对同刻兼容动作逐项提交并记录bool；每次核对原生状态，再统一推进。批次仅是便捷封装，不能作为原子提交。
3. 相同command_id不重放；相同槽位update与新增疗程分开。每条药物输入明确剩余体积和终止计划，累积剂量另记账。
4. 呼吸设备切换先停旧设备，推进并确认Free后再开新设备；这通常需要一个时间步，不能把Off+On同刻提交就认为已完成断开。该切换流程建议仍需逐设备补充验证。
5. 每次advance检查返回值、错误和事件；失败后标记当前状态不确定/故障，保留快照，不自动重放整批、不把失败当死亡；进行可诊断恢复或从已知检查点新建分支。
6. 分开记录“已接受”“仍活跃/已自然结束”“模型输出变化”“满足任务终点”。临床约束与资源调度由301层承担；不引入额外人工审批。

## 尚未验证的问题与下一步建议

优先只补足项目将实际使用的白名单：受伤Soldier下氧疗、针刺、胸管、血液/红细胞、具体呼吸机模式的配对S4；逐种设备安全切换；同药推注中途覆盖和非整数时长/袋尾质量核算；所有拟使用药物的PK/PD终点与目标剂量范围。其余未知组合在`conflict_matrix.csv`保留“未知/尚未验证”，不要默认允许。

本次没有全量重建、没有改301业务代码或既有实验数据，没有外网材料替代本地证据。研究目录之外仅进行了只读检查及原有环境加载。所有新增原生引擎日志写入本研究目录。


对照曲线见 [physiology_comparison.png](physiology_comparison.png)，可编辑图见 [SVG](physiology_comparison.svg)。

额外模型限制证据：`DrugModel.cpp:615–623`的血浆浓度计算说明自身带有“concentration computation ... known issue”注释。它提示药代输出还需要独立验证；本次S4不应被提升为定量药代或临床剂量准确性认证。产物核对脚本`tests/verify_outputs.py`完成55项证据一致性检查，结果保存在`artifact_validation.json`；这些是产物核对，不是新增55个生理实验。
