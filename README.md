# 漏磁信号分析 / MFL Signal Analysis

独立 Python 项目，用于缺陷钢筋漏磁 CSV 的批量预处理、波形对比与探索性候选分析。

## 快速开始

需要 Python 3.10+。在项目文件夹打开终端：

```powershell
python -m pip install -r requirements.txt
python mfl_analysis.py
```

将待处理的原始漏磁 CSV 放入项目 `input/`，再运行程序或双击 `运行批量处理.bat`。程序只扫描 input 顶层 CSV，结果按输入文件名和运行时间分别保存到项目 `output/`。每份文件全部处理成功后，原始 CSV 自动移入 `input_pre/`，内容保持不变；失败或跳过的文件留在 input。同名归档加编号，不覆盖已有文件。需要重做时，把归档文件复制回 input。也可指定其他输入文件夹：

```powershell
python mfl_analysis.py "D:\你的数据文件夹"
```

指定外部文件夹时，结果仍默认写入项目 output，外部原文件保留原位；自动归档仅作用于项目 input 内的文件。可用 --out 更改结果目录。单个文件失败不会阻断批次；batch_summary 记录处理状态、结果目录、原始文件校验值及归档路径。归档失败单独标为 archive_failed，已完成结果保留，原文件仍留在 input。

## 当前功能与默认值

- 输入列：ts、pos、f9–f15；UTF-8 或 GB18030 编码。未使用的 f1–f8 排除。
- 初步分析范围：10<pos<800；最长连续严格单向运动片段。
- 按位置 1 单位线性重采样；单位从配套 manifest.json 读取。
- SG 一阶、81 点估计并扣除基线；10 点均值滤波。
- 比较 SG 81/121 点及均值 1/3/5/10 点；评价峰值保留与峰位移动。
- 保留 f13 参考正峰检测；额外逐通道搜索正峰和负谷，按邻近位置分组。
- 可选真实缺口标注、人工确认无缺陷区和已知通道位置偏移。
- 径向差分默认关闭，仅在确认同分量、不同径向提离高度的配对后启用。

详细命令见 [批量使用说明](docs/批量版使用说明.md) 和 [参数与评价说明](docs/新版使用说明.md)。后者旧版的文件选择框说明已由批量版替代。模板位于 templates/。

## 项目结构

```text
mfl_analysis.py           批量入口与主信号处理流程
mfl_enhancements.py       多参数、多通道和标注评价
requirements.txt         依赖
运行批量处理.bat          Windows 启动入口
docs/                    使用说明及研究上下文
templates/               缺口标注和偏移模板
tests/                   合成信号回归测试
input/                   人工放入待处理原始 CSV
input_pre/               成功处理后的原始 CSV 归档
output/                  处理结果 CSV、波形图及汇总表
```

## 测试

```powershell
python tests/test_signal_workflow.py
python tests/test_input_workflow.py
```

测试使用合成信号，不依赖私有实测文件。覆盖正负峰、已知偏移、分组跨度、一对一匹配、边界、空候选和常量信号。

## 结果解释

候选峰、邻近分组都不是确认缺陷；一个双极响应可产生多个组。滤波可能压低峰值，参数比较不会自动证明最优参数。没有实物标注及独立验证数据时不声称检测准确率。缺口深度、宽度、通道方向及配对不能由程序自动确定。

项目已初始化本地 Git。原始 CSV、生成结果、虚拟环境和缓存不纳入版本管理。未创建远程仓库。

## 历史文件

archive/previous_outputs/ 保存迁入前的分析结果、波形图片和各版本压缩包，仅供追溯，不进入 Git。日常运行使用项目根目录的程序；新结果生成在 output/。原位置保留备份。

## output 文件与字段说明

### 先看哪些文件

先打开 `output/batch_summary_运行时间.csv`，确认对应输入的状态；再进入它记录的 `output_directory`。通常为 `output/原始文件名/run_运行时间/`。`run_...` 是运行时间，不是采样时间。不同运行使用独立目录，比较时应核对输入和参数是否一致。

| 文件 | 用途与每行代表什么 |
| --- | --- |
| `batch_summary_运行时间.csv` | 位于 output 根目录；每行是一份输入文件的处理和归档状态 |
| `processed_signals.csv` | 核心波形数据；每行是一个重采样位置，包含七路处理各阶段的信号 |
| `processing_comparison.png` | 七路信号的背景拟合与处理前后对比 |
| `candidate_peaks.csv` | 参考通道的候选正峰；每行一个峰，默认参考通道为 f13 |
| `candidate_features.csv` | 候选正峰附近的波形特征；每行对应“一个参考候选窗口 × 一个通道” |
| `reference_candidates.png` | 参考通道处理后波形及候选位置 |
| `all_channel_extrema.csv` | 七路的候选正峰、负谷；每行一个极值 |
| `multichannel_groups.csv` | 邻近极值分组；每行一个位置组 |
| `multichannel_candidates.png` | 七路候选极值在位置轴上的分布 |
| `parameter_comparison.csv` | 每行对应“一个分析窗口 × 一个通道 × 一个 SG 窗口 × 一个均值窗口”的峰值与峰位变化 |
| `parameter_comparison.png` | 参考通道在不同 SG、均值窗口下的波形对照 |
| `background_comparison.csv` | 每行对应一个通道和一组滤波参数的背景标准差；未指定背景区时只有表头 |
| `analysis_summary.json` | 实际参数、选定数据范围、阈值、单位及运行详情，供追溯 |
| `结果说明.md` | 本次结果的中文摘要 |
| `label_matches.csv`、`label_metrics.json` | 仅提供 `--labels` 实物标注后生成：逐缺口匹配与总体评价 |
| `radial_difference.csv` | 仅显式提供 `--radial-channels` 后生成：指定通道的径向差分结果 |
| `FAILED.txt` | 处理失败时生成：错误堆栈；同目录其他输出可能不完整 |

日常看波形，优先打开 `processing_comparison.png`；要在 Excel、Origin 或 Python 重新绘图，使用 `processed_signals.csv` 的 `pos` 作 X、`f9_processed` 至 `f15_processed` 作 Y。

### 通用单位、符号与空值

以下用 **X 单位**表示原始 pos 的位置单位，用 **Y 单位**表示输入通道的信号单位。程序读取适用的 `manifest.json` 中的 `position_unit` 和 `signal_unit` 作为标签，不做单位换算；找不到时显示“原始位置单位”和“原始信号单位”。只有确认元数据分别为 mm、Gs，才可把位置和幅值标成 mm、Gs。数值列本身通常不附带单位，需结合 JSON 的 `units`。

`pos` 是位置坐标，不是时间、采样序号或距起点的自动归零距离。输出按位置递增排列，即使实际扫描方向是递减。负信号代表该通道相对所估基线的负向响应，不能直接解释为缺陷更深或更浅。

CSV 空白、JSON `null` 表示未提供、未计算或当前条件下无定义，不等于 0。只有表头的候选表表示没有找到相应候选，不能证明无缺陷；背景表只有表头通常是未指定无缺陷区。候选编号 `C1` 与位置组编号 `G1` 属于不同体系，不能直接按数字关联。

### 1. 批次汇总 batch_summary

| 列名 | 含义 |
| --- | --- |
| `input_file` | 处理前原始 CSV 的完整路径；成功归档后这个路径可能已不存在 |
| `status` | `success`：处理完成且应执行的归档成功；`failed`：输入或处理失败；`skipped`：批量扫描时缺少原始信号列而跳过；`archive_failed`：处理完成但归档失败，原件留在 input |
| `output_directory` | 此文件本次结果目录；跳过的文件一般为空 |
| `resampled_rows` | 处理结果的位置采样点数，不是原始行数或缺陷数 |
| `archived_file` | 成功归档后的原始 CSV 路径；同名文件可带编号，外部输入不自动归档时为空 |
| `source_sha256` | 项目 input 中原始 CSV 的 SHA-256 内容校验值，用来核对归档完整性，不是信号特征 |
| `message` | 处理提示、候选数或具体错误原因 |

`failed` 对应的中间结果不可作为完整分析结果。`archive_failed` 的处理结果已完成，但需要检查原文件占用、权限等归档原因。`success` 只代表程序流程完成。

### 2. 完整波形 processed_signals.csv

默认共 30 列：位置与边界标记 2 列，加上七个通道各 4 列。下表中的 `fN` 依次取 f9、f10、f11、f12、f13、f14、f15。

| 列名 | 含义与单位 |
| --- | --- |
| `pos` | 在选定单向扫描片段内等间距重采样的位置，X 单位 |
| `filter_edge` | 主流程滤波边界标记：1 为边界影响区，0 为主流程内部区域；不是缺陷标签 |
| `fN_resampled` | 将选定原始通道按位置线性插值得到的波形，Y 单位；不是原 CSV 的逐行拷贝 |
| `fN_baseline` | SG 拟合得到的缓变背景估计，Y 单位；是模型估计，不是独立测得的背景真值 |
| `fN_detrended` | 去背景信号，等于 `fN_resampled - fN_baseline`，Y 单位 |
| `fN_processed` | 对去背景信号做均值滤波后的最终波形，Y 单位 |

处理顺序为 **位置重采样 → SG 估计背景 → 原波形减背景 → 均值滤波**。默认 SG 为 81 点一阶，均值为 10 点。该文件不输出原始时间列；原始时间仍在 input_pre 的原件中。

主流程每侧边界点数为 `sg_window // 2 + ceil(mean_window / 2)`，默认 45 点。多通道候选和参数对照采用所有有效对照窗口中的最大窗口，默认每侧排除 65 点，因此 `filter_edge=0` 不保证该点也参与增强分析。实际数值分别见 JSON 的 `excluded_edge_points_each_side` 和 `enhancements.common_edge_points`。

### 3. 参考候选 candidate_peaks.csv

| 列名 | 含义与单位 |
| --- | --- |
| `candidate_id` | 参考正峰序号；图中 C1、C2 等的数字 |
| `reference_channel` | 搜索正峰的参考通道，默认 f13 |
| `reference_pos` | 候选峰位置，X 单位 |
| `processed_peak` | 此位置参考通道的最终处理幅值，Y 单位 |
| `prominence` | 峰突出度：相对于周围谷底形成的局部基准，峰突出多少，Y 单位；不是幅值本身，也不是信噪比 |

参考候选需同时通过相对中位数高度、突出度、最小峰间距和主流程边界筛选。这里仅搜索正峰，不能覆盖其他通道独有异常或负谷。候选位置没有进行可选通道偏移校正。

### 4. 候选窗口特征 candidate_features.csv

每个参考候选位置周围取 `±feature_radius` 的窗口，默认 ±25 X 单位，对 f9–f15 分别提取特征。因此两个参考候选通常对应 14 行。窗口不随各通道自动重新定位，不使用可选偏移校正。

| 列名 | 含义与单位 |
| --- | --- |
| `candidate_id` | 关联 candidate_peaks 的候选编号 |
| `reference_pos` | 用来建立窗口的参考候选位置，X 单位 |
| `channel` | 本行特征对应的通道 |
| `window_left`、`window_right` | 实际取到的窗口首尾位置，X 单位；受现有数据范围限制 |
| `positive_peak` | 窗口内最终处理信号的最大值，Y 单位；字段名虽称正峰，数值未必大于零 |
| `positive_peak_pos` | 上述最大值位置，X 单位 |
| `negative_peak` | 窗口内最终处理信号的最小值，Y 单位；数值未必小于零 |
| `negative_peak_pos` | 上述最小值位置，X 单位 |
| `peak_to_peak` | 最大值减最小值，Y 单位；不是参考峰幅值 |
| `peak_valley_spacing` | 最大值位置与最小值位置之差的绝对值，X 单位；不能直接等同缺口宽度 |
| `rms` | 窗口内最终处理幅值的均方根：`sqrt(mean(processed²))`，Y 单位 |
| `energy_integral` | 对最终处理信号平方沿位置做梯形积分，单位为 Y²·X；是波形强度特征，不是焦耳意义的物理能量 |
| `raw_local_peak_to_peak` | 同一窗口内重采样信号的最大值减最小值，Y 单位；仍包含背景 |

这些窗口可能包含滤波边界点，本表没有单独排除它们；边缘附近的特征需结合 processed_signals 的标记核对。最大值、最小值也不保证是独立局部极值，窗口端点可能取到最大或最小值。

### 5. 所有通道极值 all_channel_extrema.csv

| 列名 | 含义与单位 |
| --- | --- |
| `channel` | 极值所在通道 |
| `polarity` | `positive`：相对该通道内部中位数的正向峰；`negative`：负向谷 |
| `measured_pos` | 波形上测得的极值位置，X 单位 |
| `corrected_pos` | 校正位置，等于 `measured_pos - 该通道已知偏移`；未提供偏移时与 measured_pos 相同，X 单位 |
| `amplitude` | 极值位置的最终处理信号值，Y 单位；保留符号，未再减检测中位数 |
| `prominence` | 极值突出度；负谷在信号反号后计算，Y 单位 |
| `threshold` | 该通道用于相对中位数高度和突出度筛选的阈值，Y 单位 |
| `group_id` | 所属邻近位置组编号，关联 multichannel_groups；CSV 中可能显示为 1.0 等 |

阈值主要按 `peak_sigma × 1.4826 × median(abs(z - median(z)))` 计算，并设一个防止零阈值的数值下限。MAD 尺度是这次波形内部的稳健离散程度，不是确认无缺陷区的标准差；阈值不是检出概率或置信度。

### 6. 位置分组 multichannel_groups.csv

| 列名 | 含义与单位 |
| --- | --- |
| `group_id` | 分组编号，与 all_channel_extrema 对应；参数表中使用 G1、G2 等 |
| `group_center` | 组中心：先求组内各通道校正位置的中位数，再求这些通道中位数的中位数，X 单位 |
| `left`、`right` | 组内校正位置的最小值和最大值，X 单位；不是实物缺口两端 |
| `support_count` | 该组涉及的不同通道数；同通道多个峰谷只算一个支持通道 |
| `channels` | 参与分组的通道名称，以逗号分隔 |
| `extrema_count` | 组内极值总数；同一通道的多个极值分别计数 |

分组按校正位置排序，限制整组最大跨度不超过 `merge_distance`，默认 25 X 单位。组中心是便于核对的位置摘要，尚未经缺陷定位标定。一个缺陷的正负两瓣可能分成两组，多个相邻缺陷也可能合组，所以不能把组数当成缺陷数。

### 7. 参数对照 parameter_comparison.csv

无标注时围绕分组中心建立窗口；有标注时改为围绕位于共同位置范围内的标注中心建立窗口。窗口再与共同滤波内部区域取交集，少于 3 个点则不写入该行。是否参与参数对照不等于是否满足标注匹配的完整容差窗口条件。

| 列名 | 含义与单位 |
| --- | --- |
| `window_id` | `G编号` 表示位置组；`T:缺口编号` 表示来自用户实物标注 |
| `center` | 分组或标注的窗口中心，X 单位；计算各通道窗口时会加回该通道偏移 |
| `channel` | 本行比较的通道 |
| `sg_window` | SG 背景拟合窗口的采样点数，不是时间长度 |
| `mean_window` | 均值窗口的采样点数；1 表示不做均值平滑 |
| `polarity` | 在本窗口、当前 SG 背景的去背景信号中，以绝对值最大点确定的比较极性 |
| `detrended_peak_abs` | 该去背景参考峰的绝对值，Y 单位 |
| `smoothed_same_polarity_peak` | 平滑后沿同一极性搜索的最大响应；负极性时使用反号值，Y 单位。极端情况下同极性响应消失时可为负 |
| `retention_percent` | `100 × smoothed_same_polarity_peak / detrended_peak_abs`，单位 %；分母接近 0 时留空 |
| `peak_shift` | 平滑后峰位置减去去背景参考峰位置，X 单位；正值表示向较大位置移动，不代表时间延迟 |
| `window_touches_edge` | True 表示拟取的完整窗口超出共同内部区域，实际用于比较的窗口被截短；不是缺陷标记 |
| `detrended_peak_pos` | 去背景参考峰的测得位置，X 单位 |
| `smoothed_peak_pos` | 平滑后同极性最大响应的测得位置，X 单位 |

例如保留率 70% 表示当前窗口、当前 SG 背景下平滑后同极性响应约为平滑前的 70%，不表示保留了 70% 的缺陷信息或检出率为 70%。同一 SG 窗口内比较均值窗口，才是在固定基线下观察平滑影响；改变 SG 窗口会改变背景、参考极性及峰位置。峰位变化也可能是窗口内换到了另一个峰，不一定是同一个物理峰平移。

### 8. 背景对照 background_comparison.csv

只有用 `--background-range 左端 右端` 指定人工确认无缺陷区后才有数据，可重复指定多个区间。程序合并这些区间，与共同内部区域取交集，至少需要 3 个位置采样点。

| 列名 | 含义与单位 |
| --- | --- |
| `channel` | 通道名称 |
| `sg_window`、`mean_window` | 本行对应的滤波窗口点数 |
| `background_samples` | 参与背景统计的重采样点数 |
| `std_before` | 同一 SG 背景下，均值滤波前的去背景信号样本标准差，Y 单位，使用 ddof=1 |
| `std_after` | 均值滤波后对应信号的样本标准差，Y 单位 |
| `std_ratio` | `std_after / std_before`，无单位；分母接近 0 时留空 |

例如 std_ratio=0.5 表示所选背景区标准差降为一半。这不是整段信噪比，也不能单独证明该参数最佳，应结合峰值保留率和峰位变化。

### 9. 四张波形或候选图怎么读

| 图名 | 读图方式 |
| --- | --- |
| `processing_comparison.png` | 7 行对应 f9–f15。左列为重采样波形和 SG 背景；右列为去背景波形和最终均值滤波波形。X 为位置，Y 为信号值。灰区是主流程滤波边界；各行右图的红虚线都来自参考通道候选位置，并非各通道独立检出的位置 |
| `reference_candidates.png` | 只画参考通道最终波形；C1、C2 等标注对应 candidate_peaks 的编号和位置 |
| `parameter_comparison.png` | 每个子图使用一个 SG 窗口，不同曲线表示不同均值窗口；只画参考通道。用来观察噪声、峰幅和峰形的变化，不是七通道汇总图 |
| `multichannel_candidates.png` | 横轴为位置（有偏移时为校正位置），纵轴是通道名称而非幅值。蓝色上三角为正峰、橙色下三角为负谷，灰色带是邻近分组；提供标注时绿色虚线是实物标注位置 |

不同通道的纵轴量程可能不同，不能仅凭曲线视觉高度比较幅值。参数对照图展示完整波形，但表格及增强候选分析使用共同内部区域。

### 10. 运行详情 analysis_summary.json

| 字段 | 含义 |
| --- | --- |
| `source` | 处理前的原始文件路径，归档后的实际路径见批次汇总 |
| `parameters` | 本次命令参数；包括默认值，详见下表 |
| `units.position`、`units.signal` | 位置和信号单位标签 |
| `input_encoding` | 读取原始 CSV 实际使用的编码 |
| `input_rows`、`input_duration_s` | 原始数据行数、最后时间戳减第一时间戳得到的总时长（秒） |
| `selected_rows` | 实际选中扫描片段的原始采样点数 |
| `selected_original_rows_1based_including_header` | 选中片段在原 CSV 的起止行号，第一行为表头，行号从 1 开始 |
| `selected_time_s` | 片段起止时间，相对于输入第一条时间戳的秒数 |
| `selected_pos_range` | 选中原始片段最小、最大位置；不一定等于重采样网格首尾 |
| `scan_direction` | 原始扫描方向：increasing 为位置递增，decreasing 为递减 |
| `position_runs_found` | 位置范围筛选后，按不连续行或时间间隔分开的连续片段数；不是缺陷数 |
| `resampled_rows` | 重采样后的点数 |
| `original_spacing_min_median_max` | 选中片段按位置升序后的相邻原始位置间隔最小值、中位数、最大值，X 单位 |
| `sg_window_endpoint_span`、`mean_window_endpoint_span` | 窗口首尾跨度，分别为 `(窗口点数-1) × step`，X 单位 |
| `excluded_edge_points_each_side` | 主流程每侧不参与参考峰检测的边界点数 |
| `reference_robust_scale` | 参考通道主流程内部区域的 1.4826×MAD 尺度，Y 单位 |
| `prominence_threshold` | 主流程参考候选的突出度阈值，也用于相对中位数高度筛选，Y 单位 |
| `height_threshold` | 参考波形中位数加上述阈值得到的绝对高度门槛，Y 单位 |
| `candidates` | candidate_peaks 表中记录的 JSON 形式 |
| `radial_processing` | 是否执行径向差分及指定顺序 |
| `limitations` | 本流程解释限制 |
| `actual_output_directory` | 本次实际结果目录；比 parameters.out 更直接 |
| `enhancements.version` | 增强模块的内部版本标记，当前为 2.0，不代表整个项目版本 |
| `enhancements.thresholds` | 各通道增强检测的 median（内部中位数）、mad_scale（1.4826×MAD）和 threshold（筛选阈值），均为 Y 单位 |
| `enhancements.extrema_count`、`enhancements.group_count` | 多通道候选极值总数、位置分组数 |
| `enhancements.offsets` | 用户提供的通道位置偏移，X 单位；空对象表示未提供 |
| `enhancements.common_edge_points` | 多通道及参数对照每侧排除的共同边界点数 |
| `enhancements.skipped_sg_windows` | 因超过重采样长度而未参与比较的 SG 窗口点数 |
| `enhancements.label_metrics` | 标注评价摘要，未提供标注则为 null |
| `enhancements.report` | 增强分析的中文说明 |

参考候选与多通道候选的内部区域不同，因此即使是同一参考通道，两套 MAD 和阈值也可能不同。

`parameters` 中各项的含义：

| 参数字段 | 含义 |
| --- | --- |
| `input`、`out` | 本次输入文件路径和用户指定的输出选项；out=null 表示使用默认输出位置 |
| `pos_min`、`pos_max`、`step` | 位置筛选下上限（严格不含端点）、重采样间距，X 单位 |
| `sg_window`、`sg_order`、`mean_window` | 主流程 SG 点数、拟合阶数和均值点数 |
| `peak_sigma` | MAD 尺度阈值乘数，无单位 |
| `peak_distance` | 同一通道同一极性检测的最小峰间距，X 单位；不是缺陷间距保证 |
| `feature_radius` | 特征和参数比较窗口的半径，X 单位 |
| `reference` | 参考通道名称 |
| `radial_channels` | 用户指定径向通道顺序；null 表示未启用 |
| `compare_means`、`compare_sg_windows` | 请求比较的窗口点数列表；程序还会纳入主流程窗口及均值 1 点，实际组合见参数表 |
| `labels`、`labels_complete` | 实物标注 CSV 路径，以及是否声明完整覆盖所有缺陷 |
| `background_range` | 已确认无缺陷的位置区间列表 |
| `channel_offsets` | 通道偏移 JSON 文件路径，具体数值见 enhancements.offsets |
| `merge_distance` | 邻近分组允许的最大组内位置跨度，X 单位 |
| `overwrite` | 是否显式允许覆盖同名结果；默认 false |

### 11. 可选标注匹配 label_matches.csv 与 label_metrics.json

仅指定实物标注后生成。匹配采用一对一：每个缺口最多对应一个位置组，每组最多匹配一个缺口，优先匹配更多缺口，再最小化归一化位置误差。只评价整个“标注位置 ± tolerance”窗口都在所有通道共同可评价范围内的缺口。

| label_matches 列 | 含义 |
| --- | --- |
| `defect_id` | 用户提供的真实缺口编号 |
| `actual_pos` | 实物标注位置，X 单位 |
| `status` | matched：容差内成功匹配；missed：可评价但未匹配；outside_evaluable_range：完整容差窗口不在可评价区域内 |
| `matched_group` | 匹配的位置组编号，未匹配或被排除时为空 |
| `error` | `匹配组中心 - actual_pos`，带符号的位置误差，X 单位；未匹配时为空 |

| label_metrics 字段 | 含义 |
| --- | --- |
| `evaluable_defects` | 满足可评价范围条件的标注缺口数 |
| `excluded_groups_outside_range` | 因组中心位于共同可评价范围之外而排除的位置组数 |
| `matched`、`missed` | 可评价标注中匹配成功与未匹配的数量 |
| `recall` | matched / evaluable_defects，0–1；没有可评价标注则为 null。标注不完整时只反映已提供标注的匹配情况 |
| `unmatched_groups` | 可评价范围内未匹配标注的位置组数 |
| `false_positive_groups` | 只有 labels_complete=true 才将未匹配组计入此项，否则为 null |
| `precision` | 完整标注时 matched / 范围内位置组数，0–1；无完整标注或没有组时为 null |
| `fpr` | 当前始终为 null：没有定义无缺陷样本总数，不计算假阳性率 |
| `note` | 评价前提与限制说明 |

这些指标评价当前分组和标注的匹配，不是自动验证过的普适检测准确率。标注中的深度、宽度等附加列目前不用于尺寸反演，也不会自动变成上述输出指标。

### 12. 可选径向差分 radial_difference.csv

只有实验布置确认通道测量同一磁场分量、对应不同径向提离高度时才应显式启用。默认不生成此文件。

| 列名形式 | 含义 |
| --- | --- |
| `pos`、`filter_edge` | 与主波形文件相同的位置与主流程边界标记 |
| `fB_minus_fA_raw` | 用户指定顺序中后一通道减前一通道的重采样差分，Y 单位。例如 f10_minus_f9_raw=f10_resampled−f9_resampled |
| `fB_minus_fA_processed` | 对该差分做 SG 去背景、再均值滤波的结果，Y 单位 |
| `combined` | 各相邻差分处理结果之和，Y 单位；相同线性处理下等于指定末通道减首通道后的处理结果 |

combined 不是多路独立信号平均，也不能据此声称信噪比自动提高相同倍数。启用此项会额外输出差分文件，主波形和现有候选表仍按原来的逐通道流程生成。

### 当前已有运行示例（固定记录，不代表未来运行）

`t_s1_c2_n73_1790052371 / run_20260926_171002_856257` 的记录：输入 2370 点，选中 1160 点，位置重采样后 789 点；参考 f13 有 2 个候选正峰（位置 109、403）；七路共 32 个候选极值，分成 5 组。这不表示试件只有 2 个缺陷或有 5 个缺陷。

这次没有提供确认的无缺陷区，所以 background_comparison 只有表头；未提供标注或启用径向差分，所以没有对应的可选文件。JSON 中单位为“原始位置单位／原始信号单位”，本次输出没有从配套元数据获得明确单位标签。需要正式标注 mm、Gs 时，应先核对适用的原始 manifest，再用于后续运行。
