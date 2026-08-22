# Experiment 001

Title:

Understanding and reproducing FlashFuzz


Date:

2026-07-29


## Goal

学习FlashFuzz代码结构，为后续复现实验做准备。


## Repository

Location:

~/FlashFuzz


GitHub:

https://github.com/ncsu-swat/FlashFuzz



## Completed


[x] Clone repository


[x] Read README.md


[x] Analyze run.py


[x] Analyze expmanager.py



## Understanding


### run.py


Role:

Experiment entry point.


Responsibilities:

- Select DL framework
- Select version
- Read API list
- Create Experiment objects



### expmanager.py


Role:

Experiment manager.


Responsibilities:

- Manage Docker container
- Schedule experiments
- Collect results



## Current questions


1. Where is harness generated?


2. How does LLM receive API information?


3. Where should historical bug pattern be inserted?



## Next step


Analyze:

testharness_generation/torch_cpu

##
实验阶段：FlashFuzz源码理解
日期：7.29

目标：
理解FlashFuzz整体执行流程，为后续复现实验准备。

完成内容：

1. 理解run.py
- 负责解析实验参数
- 读取API列表
- 创建Experiment对象

2. 理解expmanager.py
- Experiment管理单个API实验
- Scheduler负责并行调度

3. 理解LLM harness生成流程
- llm_gptoss.py负责生成main.cpp
- prompt包含API信息和helper模板

4. 理解编译流程
- build_test_harness.py
- clang++ + libFuzzer
- 生成fuzz可执行文件

5. 理解fuzz流程
- fuzz.sh启动libFuzzer
- 输入mutation
- coverage反馈
- crash保存

当前实验状态：

FlashFuzz代码结构已理解。
下一步：
配置实验环境并运行单API测试。
