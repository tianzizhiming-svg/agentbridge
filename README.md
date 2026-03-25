# AgentBridge

[![402 Index](https://img.shields.io/badge/402%20Index-AgentBridge-blue)](https://402index.io/directory?search=AgentBridge)

AI agents pay-per-fetch to access Chinese web content (Xiaohongshu, Zhihu, etc.) — returns clean markdown, settled in USDC on Base via x402.

## 🚀 当前状态

✅ **技术验证完成** — 已跑通 AI 代理 → AgentBridge → ReqCast → 链上 USDC 收款完整闭环

**链上收款记录：** 已成功收款 4 笔，合计 0.13625 USDC  
🔗 [查看链上验证记录](./docs/verification.md)
- 💰 **Price:** $0.003 per request (USDC on Base)

## 🎯 项目定位

AgentBridge 是一个轻量中间层，让 AI 代理能够：
- 自动识别需要支付的场景
- 通过 x402 协议发起支付请求
- 在 Base 链上完成 USDC 结算

**一句话：让 AI 代理自己付钱。**

## 🤝 生态背书

- ✅ **ReqCast 官方对接** — 已完成端到端生产环境验证
- ✅ **x402 生态贡献者** — 参与 [awesome-x402](https://github.com/xpayash/wesome-x402) 建设
- ✅ **Base 链** — 基于 Base Mainnet 运行

## 🧱 技术栈

| 组件 | 说明 |
|------|------|
| x402 协议 | 支付请求标准化协议 |
| ReqCast | 支付执行层，提供回调验证 |
| Base 链 | L2 低成本结算 |
| USDC | 支付代币 |

## 🔁 工作流程
