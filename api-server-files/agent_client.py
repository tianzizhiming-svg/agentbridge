import base64
import json
import secrets
import time
import requests
from eth_account import Account

# ================= 配置区 =================
API_URL = "http://localhost:8000/v1/api/industry"
PRIVATE_KEY = "8e3bdb2b4728d2def3b216f9064c49820b259fd4a7542b753f263b20779b1c42"  # ⚠️ 替换为你的完整测试私钥 (带不带 0x 均可)

# USDC on Base 合约地址
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
# ==========================================


def get_signed_authorization(private_key: str, to_address: str, amount_micro_usdc: str):
    """使用私钥在本地进行 EIP-3009 TransferWithAuthorization 签名"""
    if not private_key.startswith("0x"):
        private_key = f"0x{private_key}"

    account = Account.from_key(private_key)
    from_address = account.address

    # 1. 生成 32 字节随机 nonce
    nonce_bytes = secrets.token_bytes(32)
    nonce_hex = "0x" + nonce_bytes.hex()

    # 2. 时间戳 (单位: 秒)
    valid_after = 0
    valid_before = int(time.time()) + 3600

    # 3. EIP-712 类型与域定义
    types = {
        "TransferWithAuthorization": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ]
    }

    domain = {
        "name": "USD Coin",
        "version": "2",
        "chainId": 8453,
        "verifyingContract": USDC_CONTRACT,
    }

    # EIP-712 签名计算传入 raw bytes 与 int
    message = {
        "from": from_address,
        "to": to_address,
        "value": int(amount_micro_usdc),
        "validAfter": valid_after,
        "validBefore": valid_before,
        "nonce": nonce_bytes,
    }

    # 本地静默签名
    signed = Account.sign_typed_data(
        private_key,
        domain_data=domain,
        message_types=types,
        message_data=message,
    )

    sig_hex = signed.signature.hex()
    if not sig_hex.startswith("0x"):
        sig_hex = f"0x{sig_hex}"

    # ⚠️ CDP OpenAPI 规范：authorization 内部所有数值均必须为字符串 (str)
    authorization = {
        "from": from_address,
        "to": to_address,
        "value": str(amount_micro_usdc),
        "validAfter": str(valid_after),    # 转为字符串 "0"
        "validBefore": str(valid_before),  # 转为字符串时间戳
        "nonce": nonce_hex,
    }

    return sig_hex, authorization


def agent_execute_query():
    print(f"🤖 Agent 启动，准备查询: {API_URL}")
    proxies = {"http": None, "https": None}

    # 1. 发起初始 GET 请求获取 402 支付挑战
    res = requests.get(API_URL, proxies=proxies)
    if res.status_code != 402:
        print(f"❌ 未返回 402 支付挑战，状态码: {res.status_code}, 内容: {res.text}")
        return

    print("✅ 收到 402 Payment Required，解析支付要求...")

    payment_header = res.headers.get("PAYMENT-REQUIRED")
    challenge = json.loads(base64.b64decode(payment_header)) if payment_header else res.json()
    accept_item = challenge["accepts"][0]

    pay_to = accept_item["payTo"]
    amount = str(accept_item["amount"])

    print(f"💰 需支付: {amount} micro-USDC -> {pay_to}")

    # 2. 生成本地签名
    print("🔐 Agent 正在内存中使用私钥进行 EIP-3009 签名...")
    sig_hex, authorization = get_signed_authorization(PRIVATE_KEY, pay_to, amount)
    print(f"✍️ 签名完成: {sig_hex[:20]}...")

    # 3. 构造符合 Coinbase CDP x402 V2 标准的 Payload
    payment_payload = {
        "x402Version": 2,
        "accepted": accept_item,  # 原样带回 402 响应中的 accept 项
        "payload": {
            "signature": sig_hex,
            "authorization": authorization,
        },
    }

    # 4. 打包 Header 并重新发送请求
    x_payment_b64 = base64.b64encode(json.dumps(payment_payload).encode("utf-8")).decode("utf-8")
    headers = {
        "X-Payment": x_payment_b64,
        "Content-Type": "application/json",
    }

    print("🚀 带着签名重新请求数据 (POST)...")
    final_res = requests.post(API_URL, json={"keyword": "GDP"}, headers=headers, proxies=proxies)

    if final_res.status_code == 200:
        print("\n🎉 支付校验成功，获取到数据:")
        print(json.dumps(final_res.json(), indent=2, ensure_ascii=False))
    else:
        print(f"\n❌ 请求失败，状态码: {final_res.status_code}")
        print("响应内容:", final_res.text)


if __name__ == "__main__":
    agent_execute_query()
    input("\n按回车键退出...")