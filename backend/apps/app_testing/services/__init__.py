"""Service layer for the 移动端 App 测试 module.

``sonic_client``   - Sonic HTTP 客户端（登录/续期、设备、套件、ElementPages）
``case_converter`` - AITS 步骤 <-> Sonic 步骤双向转换 + runSuite payload 组装
``execution``      - execute_suite / execute_case 执行编排（DB + 报告 + WS）
``generator``      - 自然语言 -> App 用例步骤（AI 优先，规则降级）
"""
