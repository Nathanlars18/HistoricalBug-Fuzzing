## Date: 2026-08-03

# Exp002 FlashFuzz PyTorch Baseline Reproduction

## 1. Experiment Objective

本实验目标是复现 FlashFuzz 在 PyTorch CPU API 上的自动化 fuzzing 流程，为后续“历史 Bug Pattern 增强 Harness”的研究建立 baseline。

主要验证以下内容：

1. FlashFuzz harness 自动生成流程是否能够正常运行；
2. PyTorch C++ API 是否能够被 libFuzzer 调用；
3. FlashFuzz 的 Docker 实验框架是否能够完成自动化 fuzz、结果收集；
4. 为后续多 API baseline 实验提供可运行环境。

本实验选择 PyTorch 2.2 CPU 环境进行复现。

---

# 2. Experimental Environment

详细环境配置见：

environment/dev_environment.md

本实验关键环境如下：

- Host:
  - Windows + WSL2 Ubuntu 22.04

- Container:
  - ncsuswat/flashfuzz:torch2.2-fuzz

- PyTorch:
  - PyTorch 2.2.0a0+git8ac9b20

- Build:
  - Source build
  - CPU fuzz mode

- CUDA:
  - Disabled in fuzz build
  - USE_CUDA=0

- Fuzz engine:
  - LLVM libFuzzer

- Compiler:
  - clang++

---

# 3. Initial FlashFuzz Reproduction Problems

## 3.1 API Directory Structure Mismatch

FlashFuzz 原始代码默认 API harness 位于：

/root/fuzz/
    ├── torch.add
    ├── torch.mul
    └── ...

但是当前 PyTorch CPU harness 目录结构为：

/root/fuzz/
    └── torch_cpu/
        ├── torch.add
        ├── torch.mul
        └── ...

导致 FlashFuzz 原始 copy.py 无法找到 PyTorch API 目录。

运行时出现：

No directories starting with 'torch' found!
Operation failed!

---

## 3.2 build 阶段与 run 阶段路径不一致

修改目录结构后：

harness 编译生成位置：

/root/fuzz/torch_cpu/torch.add/fuzz

但是 run.py 默认执行路径：

/root/fuzz/torch.add/fuzz

导致 fuzz 阶段无法找到正确的可执行文件。

实验表现：

Could not find the file /root/fuzz/torch.add/fuzz-0.log

同时：

rounds: 0

说明 libFuzzer 没有真正运行。

---

# 4. Modifications to FlashFuzz

## 4.1 build_test_harness.py 修改

目的：

支持指定 API 进行单独实验，避免一次构建全部 PyTorch API。

修改内容：

- 增加 API 选择支持；
- 支持通过：

--apis torch.add

指定目标 API。

同时降低并行编译数量：

修改：

```python
ProcessPoolExecutor(max_workers=64)
为：
ProcessPoolExecutor(max_workers=2)
原因：
当前实验环境资源有限，避免大量 API 并行编译造成资源压力。
4.2 copy.py 路径修改
原始代码：
glob.glob("torch.*")
默认搜索：
/root/fuzz/torch.*
修改为：
glob.glob("torch_cpu/torch.*")
使其能够匹配当前目录结构：
/root/fuzz/torch_cpu/torch.*
修改文件：
scripts/template/torch_cpu/copy.py
4.3 添加运行路径兼容软链接
由于 FlashFuzz run.py 仍使用：
/root/fuzz/torch.add
路径，
因此增加软链接：
ln -s torch_cpu/torch.add torch.add
使：
/root/fuzz/torch.add
映射到：
/root/fuzz/torch_cpu/torch.add
从而兼容 FlashFuzz 原始执行流程。
5. Experimental Procedure
5.1 Harness Build
进入 Docker：
docker exec -it flashfuzz-torch22 bash
执行：
python3 build_test_harness.py \
--dll torch \
--mode fuzz \
--ver 2.2 \
--apis torch.add \
--time_budget 60
构建结果：
Building PyTorch API: torch.add

Successfully built torch.add

Built 1/1 PyTorch APIs successfully.
生成 fuzz binary：
/root/fuzz/torch_cpu/torch.add/fuzz
检查链接：
ldd torch_cpu/torch.add/fuzz | grep torch
结果：
libtorch.so
libtorch_cpu.so
libc10.so
说明 fuzz harness 正确链接到自编译 PyTorch。
6. Baseline Experiment
6.1 Target API
本次验证 API：
torch.add
6.2 Run Command
执行：
python3 run.py \
--dll torch \
--version 2.2 \
--mode fuzz \
--apis torch.add \
--time_budget 60
7. Experimental Results
实验成功运行。
输出：
api: torch.add
rounds: 16073
invalid: 9198
valid: 6875
validity_ratio: 0.427736
结果统计：
API	Time Budget	Rounds	Valid	Invalid	Validity Ratio
torch.add	60s	16073	6875	9198	0.427736


8. Result Analysis
实验结果表明：
FlashFuzz 可以在当前 PyTorch 2.2 CPU 环境下正常运行；
自动生成的 harness 可以成功调用 PyTorch C++ API；
libFuzzer 能够持续产生测试输入；
run.py 可以完成：Docker 创建；
fuzz 执行；
日志收集；
结果统计。

单 API baseline 流程已经验证成功。
9. Problems and Solutions Summary
Problem	Cause	Solution
copy.py 无法找到 API	FlashFuzz 默认目录结构与当前环境不同	修改 API 搜索路径
build 成功但 fuzz 不运行	build/run 使用不同目录	添加 torch.add 软链接
fuzz-0.log 不存在	libFuzzer 没有真正启动	修复运行路径
大量 API 同时编译	默认并行数量过高	max_workers 调整为2


10. Current Status
已完成：

PyTorch 2.2 fuzz 环境配置

FlashFuzz Docker 环境配置

单 API harness 编译

单 API fuzz 实验运行

baseline 数据收集
当前实验状态：
FlashFuzz PyTorch CPU baseline 已成功复现。
11. Next Steps
后续计划：
扩展到约 10 个 PyTorch CPU API；
收集 baseline 指标：rounds
valid/invalid ratio
coverage
crash 数量

基于历史 PyTorch Bug Pattern 设计增强 Harness 方法；
对比：原始 FlashFuzz
History Bug Pattern Enhanced FlashFuzz

## Date 08-04

# Phase 3: 10 API Smoke Test

## Objective

在正式 baseline 实验前，验证多个 PyTorch API 的 FlashFuzz fuzz pipeline 是否能够稳定运行。

实验目标：

1. 验证 10 个 API harness 是否可以正常执行；
2. 验证 libFuzzer 是否能够产生有效测试输入；
3. 验证 run.py 是否能够完成多 API 自动化实验和结果收集。

---

## Configuration

- Framework:
  PyTorch

- Version:
  2.2

- Mode:
  fuzz

- Device:
  CPU

- Time budget:
  60 seconds per API

- Number of APIs:
  10


Selected APIs:

torch.add
torch.mul
torch.matmul
torch.mm
torch.addmm
torch.relu
torch.sigmoid
torch.softmax
torch.tanh
torch.exp

---

## Command

```bash
python3 run.py \
--dll torch \
--version 2.2 \
--mode fuzz \
--apis \
torch.add \
torch.mul \
torch.matmul \
torch.mm \
torch.addmm \
torch.relu \
torch.sigmoid \
torch.softmax \
torch.tanh \
torch.exp \
--time_budget 60
Results
API	Rounds	Valid	Invalid	Validity Ratio
torch.add	18006	6034	11972	0.335111
torch.mul	7479	4713	2766	0.630164
torch.exp	39442	20698	18744	0.524771
torch.tanh	32730	3834	28896	0.117140
torch.sigmoid	49601	29955	19646	0.603919
torch.mm	24632	0	27892	0.000000
torch.softmax	48716	23068	25648	0.473520
torch.addmm	6958	3522	3436	0.506180
torch.matmul	12277	0	22738	0.000000
torch.relu	52355	28559	23796	0.545488


Observation
All 10 selected APIs completed fuzz execution successfully.

The previous issue:

Could not find fuzz-0.log
did not appear.
This indicates that the fuzzing pipeline was successfully executed.
Different APIs show different validity ratios.
For example:
torch.sigmoid:
validity_ratio = 0.603919

torch.tanh:
validity_ratio = 0.117140

torch.mm:
validity_ratio = 0

torch.matmul:
validity_ratio = 0

Matrix multiplication APIs generated many invalid inputs, indicating that these APIs require stronger input constraints such as tensor dimension compatibility.
This observation motivates later research on historical Bug Pattern based harness enhancement.
Conclusion
The 10 API smoke test successfully validated the FlashFuzz baseline pipeline on PyTorch 2.2 CPU environment.
The environment is ready for the formal baseline experiment with a longer fuzzing time budget.

# Phase 4: Formal Baseline Fuzzing

## Configuration

Framework:
PyTorch 2.2

Backend:
CPU

Mode:
fuzz

Time budget:
300 seconds per API


Selected APIs:

- torch.add
- torch.mul
- torch.matmul
- torch.mm
- torch.addmm
- torch.relu
- torch.sigmoid
- torch.softmax
- torch.tanh
- torch.exp


## Results

| API | Rounds | Valid | Invalid | Validity Ratio |
|---|---:|---:|---:|---:|
| torch.add | 98509 | 37951 | 60558 | 0.385254 |
| torch.mul | 37179 | 28269 | 8910 | 0.760349 |
| torch.exp | 215302 | 116070 | 99232 | 0.539103 |
| torch.tanh | 189599 | 17027 | 172572 | 0.089805 |
| torch.sigmoid | 263648 | 163096 | 100552 | 0.618613 |
| torch.mm | 118274 | 0 | 152014 | 0 |
| torch.softmax | 290590 | 127468 | 163122 | 0.438652 |
| torch.addmm | 33141 | 22075 | 11066 | 0.666093 |
| torch.matmul | 62867 | 0 | 106362 | 0 |
| torch.relu | 242667 | 136331 | 106336 | 0.561803 |


## Observation

All selected APIs completed fuzzing successfully.

Matrix multiplication APIs (torch.mm and torch.matmul) generated many invalid inputs and obtained zero valid executions, suggesting that these APIs require stronger input constraints.

This motivates the later investigation of historical Bug Pattern guided harness enhancement.

# Environment Snapshot

Baseline Docker Image:

ncsuswat/flashfuzz:torch2.2-baseline

Image ID:

58b40339968b

Purpose:

This image preserves the verified FlashFuzz baseline environment before introducing historical Bug

# Environment Snapshot

## Baseline Docker Image

The verified FlashFuzz baseline environment was saved as:

ncsuswat/flashfuzz:torch2.2-baseline

Image ID:

58b40339968b

The image contains:

- PyTorch 2.2 CPU fuzzing environment
- FlashFuzz framework
- Modified harness build pipeline
- 10 selected PyTorch API fuzz harnesses

Selected APIs:

torch.add
torch.mul
torch.matmul
torch.mm
torch.addmm
torch.relu
torch.sigmoid
torch.softmax
torch.tanh
torch.exp

Purpose:

This snapshot is used as the fixed baseline environment for comparison with the later historical Bug Pattern enhanced harness generation approach.

