# -*- coding: utf-8 -*-
"""
x402 实测脚本 - 自选商品测试支付
用法:
  python test_pick.py            # 交互式选择
  python test_pick.py 2          # 直接选第2个商品
  python test_pick.py company    # 按关键词选
  python test_pick.py report     # 选报告类商品

支持两种商品类型:
  - API 类: POST 请求带 JSON body → 402 → POST 带支付 → 数据
  - 报告类: GET 请求 → 402 → POST 带支付 → .md 文件内容

关键修复: 使用 x402 v2 标准格式 (signature 拼接为单字符串, authorization 不含 v/r/s)
"""

import os
import sys
import json
import base64
import time
import secrets
import requests
from pathlib import Path

# ============================================================
# 自动读取私钥
# ============================================================

def load_private_key():
    pk = os.environ.get("PRIVATE_KEY", "").strip()
    if pk:
        return pk
    for env_path in [Path(".env"), Path("F:/afie_proxy/.env")]:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("PRIVATE_KEY") and "=" in line:
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
    return ""

PRIVATE_KEY = load_private_key()
if not PRIVATE_KEY:
    print("[ERROR] 没找到 PRIVATE_KEY")
    print("        手动设置: $env:PRIVATE_KEY = '你的私钥'")
    sys.exit(1)

if not PRIVATE_KEY.startswith("0x"):
    PRIVATE_KEY = "0x" + PRIVATE_KEY

print(f"[INFO] 私钥已加载 ({PRIVATE_KEY[:6]}...{PRIVATE_KEY[-4:]})")
print()

# ============================================================
# 商品目录
# ============================================================
SERVER_URL = "http://localhost:8000"

PRODUCTS = [
    # --- API 类商品 ($0.003 - $0.005) ---
    {"id": 1, "name": "企业信用查询", "tag": "company",
     "type": "api",
     "endpoint": "/v1/api/company", "body": {"name": "阿里巴巴"}, "price": 0.003},
    {"id": 2, "name": "宏观经济数据 - GDP", "tag": "gdp",
     "type": "api",
     "endpoint": "/v1/api/industry", "body": {"keyword": "GDP", "limit": 5}, "price": 0.005},
    {"id": 3, "name": "宏观经济数据 - CPI", "tag": "cpi",
     "type": "api",
     "endpoint": "/v1/api/industry", "body": {"keyword": "CPI", "limit": 5}, "price": 0.005},
    {"id": 4, "name": "政策搜索 - 人工智能", "tag": "policy-ai",
     "type": "api",
     "endpoint": "/v1/api/policy", "body": {"keyword": "人工智能", "limit": 5}, "price": 0.005},
    {"id": 5, "name": "政策搜索 - 新能源", "tag": "policy-energy",
     "type": "api",
     "endpoint": "/v1/api/policy", "body": {"keyword": "新能源", "limit": 5}, "price": 0.005},
    # --- 报告类商品 ($4.99) ---
    {"id": 6, "name": "AI 产业全景报告 2026", "tag": "report-ai",
     "type": "report",
     "asset_id": "report-ai-industry-2026", "price": 4.99},
    {"id": 7, "name": "消费市场全景报告 2026", "tag": "report-consumer",
     "type": "report",
     "asset_id": "report-consumer-market-2026", "price": 4.99},
    {"id": 8, "name": "新能源汽车产业报告 2026", "tag": "report-ev",
     "type": "report",
     "asset_id": "report-ev-industry-2026", "price": 4.99},
    {"id": 9, "name": "人形机器人产业报告 2026", "tag": "report-robot",
     "type": "report",
     "asset_id": "report-humanoid-robot-2026", "price": 4.99},
    {"id": 10, "name": "API 技术文档 2026", "tag": "report-api",
     "type": "report",
     "asset_id": "report-api-tech-docs-2026", "price": 4.99},
    {"id": 11, "name": "外资品牌入市指南 2026", "tag": "report-entry",
     "type": "report",
     "asset_id": "report-market-entry-2026", "price": 4.99},
    {"id": 12, "name": "新能源产业报告 2026", "tag": "report-newenergy",
     "type": "report",
     "asset_id": "report-new-energy-2026", "price": 4.99},
    {"id": 13, "name": "半导体产业报告 2026", "tag": "report-semi",
     "type": "report",
     "asset_id": "report-semiconductor-2026", "price": 4.99},
    {"id": 14, "name": "高校智能报告 2026", "tag": "report-uni",
     "type": "report",
     "asset_id": "report-university-intelligence-2026", "price": 4.99},
]

# ============================================================
# EIP-3009 / EIP-712 签名
# ============================================================

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

EIP712_DOMAIN_TYPES = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]

TRANSFER_AUTH_TYPES = [
    {"name": "from", "type": "address"},
    {"name": "to", "type": "address"},
    {"name": "value", "type": "uint256"},
    {"name": "validAfter", "type": "uint256"},
    {"name": "validBefore", "type": "uint256"},
    {"name": "nonce", "type": "bytes32"},
]


def sign_eip3009(private_key, from_addr, to_addr, amount, asset_addr, chain_id):
    from eth_account import Account

    account = Account.from_key(private_key)
    sender = account.address

    valid_after = int(time.time())
    valid_before = int(time.time()) + 3600
    nonce = "0x" + secrets.token_hex(32)

    message = {
        "types": {
            "EIP712Domain": EIP712_DOMAIN_TYPES,
            "TransferWithAuthorization": TRANSFER_AUTH_TYPES,
        },
        "domain": {
            "name": "USD Coin",
            "version": "2",
            "chainId": chain_id,
            "verifyingContract": asset_addr,
        },
        "primaryType": "TransferWithAuthorization",
        "message": {
            "from": sender,
            "to": to_addr,
            "value": amount,
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": nonce,
        },
    }

    try:
        from eth_account.messages import encode_typed_data
        encoded = encode_typed_data(full_message=message)
    except (ImportError, TypeError):
        try:
            from eth_account.messages import encode_structured_data
            encoded = encode_structured_data(message)
        except ImportError:
            encoded = _manual_eip712_hash(message)

    signed = account.sign_message(encoded)

    sig_hex = "0x" + hex(signed.r)[2:].zfill(64) + hex(signed.s)[2:].zfill(64) + hex(signed.v)[2:].zfill(2)

    authorization = {
        "from": sender,
        "to": to_addr,
        "value": str(amount),
        "validAfter": str(valid_after),
        "validBefore": str(valid_before),
        "nonce": nonce,
    }

    return sig_hex, authorization, sender


def _manual_eip712_hash(message):
    from eth_utils import keccak
    from eth_abi import encode

    domain = message["domain"]
    msg = message["message"]

    domain_type_hash = keccak(b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
    domain_hash = keccak(
        domain_type_hash
        + encode(
            ["bytes32", "bytes32", "uint256", "address"],
            [
                keccak(domain["name"].encode()),
                keccak(domain["version"].encode()),
                int(domain["chainId"]),
                int(domain["verifyingContract"], 16),
            ],
        )
    )

    struct_type_hash = keccak(
        b"TransferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce)"
    )
    nonce_bytes = bytes.fromhex(msg["nonce"][2:].zfill(64))
    struct_hash = keccak(
        struct_type_hash
        + encode(
            ["address", "address", "uint256", "uint256", "uint256", "bytes32"],
            [
                int(msg["from"], 16),
                int(msg["to"], 16),
                int(msg["value"]),
                int(msg["validAfter"]),
                int(msg["validBefore"]),
                nonce_bytes,
            ],
        )
    )

    from eth_account.messages import SignableMessage
    return SignableMessage(
        version=b"\x19\x01",
        header=domain_hash,
        body=struct_hash,
    )


# ============================================================
# 选择商品
# ============================================================

def select_product():
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(PRODUCTS):
                return PRODUCTS[idx]
        for p in PRODUCTS:
            if arg.lower() in p["tag"].lower() or arg.lower() in p["name"].lower():
                return p
        print(f"[ERROR] 没找到匹配 '{arg}' 的商品")
        sys.exit(1)

    print("=" * 55)
    print("  商品列表（想买哪个输序号）")
    print("=" * 55)
    for p in PRODUCTS:
        ptype = "[API] " if p["type"] == "api" else "[报告]"
        print(f"  {p['id']:2d}. {ptype} {p['name']}  -  ${p['price']} USDC")
    print("=" * 55)
    print()

    while True:
        choice = input(f"买哪个？输序号 (1-{len(PRODUCTS)}): ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(PRODUCTS):
                return PRODUCTS[idx]
        print("  输错了，重来")

product = select_product()

print()
print(f"[已选] {product['name']}  -  ${product['price']} USDC")
print(f"[类型] {'API 数据查询' if product['type'] == 'api' else '行业报告 (.md 文件)'}")
print()

# ============================================================
# Step 1: 获取 402 支付挑战
# ============================================================
print("[Step 1] 获取支付挑战...")

if product["type"] == "api":
    # API 类: POST 带 body 拿 402
    resp = requests.post(
        f"{SERVER_URL}{product['endpoint']}",
        json=product["body"],
        headers={"Content-Type": "application/json"},
        proxies={"http": None, "https": None},
    )
else:
    # 报告类: GET 拿 402
    resp = requests.get(
        f"{SERVER_URL}/v1/assets/{product['asset_id']}/content",
        proxies={"http": None, "https": None},
    )

if resp.status_code != 402:
    print(f"[WARN] 预期 402，收到 {resp.status_code}: {resp.text[:300]}")
    sys.exit(1)

challenge = resp.json()

accepts_list = challenge.get("accepts", [])
if accepts_list:
    accepts = accepts_list[0]
else:
    accepts = challenge

pay_to = accepts.get("payTo") or accepts.get("pay_to") or ""
amount = int(accepts.get("amount", 0))
asset = accepts.get("asset") or accepts.get("asset_address") or ""
network = accepts.get("network") or accepts.get("network_id") or ""
scheme = accepts.get("scheme", "exact")
max_timeout = accepts.get("maxTimeoutSeconds", 30)
extra = accepts.get("extra", {"name": "USD Coin", "version": "2"})
chain_id = int(network.split(":")[1]) if ":" in network else 8453

print(f"  收款: {pay_to}")
print(f"  金额: {amount / 1_000_000} USDC ({amount} micro-USDC)")
print(f"  网络: {network}")
print(f"  资产: {asset}")
print(f"  chainId: {chain_id}")
print()

if not pay_to or not asset:
    print("[ERROR] 收款地址或资产地址为空，无法签名")
    print(f"  pay_to = '{pay_to}'")
    print(f"  asset = '{asset}'")
    print(f"  challenge keys: {list(challenge.keys())}")
    sys.exit(1)

# ============================================================
# Step 2: 签名 EIP-3009
# ============================================================
print("[Step 2] 签名支付 (EIP-3009)...")

signature_hex, authorization, sender = sign_eip3009(
    PRIVATE_KEY, None, pay_to, amount, asset, chain_id
)

print(f"  付款人: {authorization['from']}")
print(f"  Nonce: {authorization['nonce']}")
print(f"  有效期: {authorization['validAfter']} -> {authorization['validBefore']}")
print(f"  签名: {signature_hex[:20]}...{signature_hex[-8:]}")
print()

# ============================================================
# Step 3: 构造 x402 v2 标准格式并提交
# ============================================================
print("[Step 3] 提交支付并获取内容...")

x402_payload = {
    "x402Version": 2,
    "scheme": scheme,
    "network": network,
    "accepted": {
        "scheme": scheme,
        "network": network,
        "amount": str(amount),
        "asset": asset,
        "payTo": pay_to,
        "maxTimeoutSeconds": max_timeout,
        "extra": extra,
    },
    "payload": {
        "signature": signature_hex,
        "authorization": authorization,
    },
    "extensions": {},
}

payment_header = base64.b64encode(
    json.dumps(x402_payload, separators=(",", ":")).encode()
).decode()

if product["type"] == "api":
    # API 类: POST 带支付 + body
    post_resp = requests.post(
        f"{SERVER_URL}{product['endpoint']}",
        json=product["body"],
        headers={
            "Content-Type": "application/json",
            "X-Payment": payment_header,
            "PAYMENT-SIGNATURE": payment_header,
        },
        proxies={"http": None, "https": None},
        timeout=30,
    )
else:
    # 报告类: POST 带支付 (不需要 body)
    post_resp = requests.post(
        f"{SERVER_URL}/v1/assets/{product['asset_id']}/content",
        headers={
            "X-Payment": payment_header,
            "PAYMENT-SIGNATURE": payment_header,
        },
        proxies={"http": None, "https": None},
        timeout=30,
    )

print(f"  状态码: {post_resp.status_code}")
print()

if post_resp.status_code == 200:
    print("[SUCCESS] 支付+结算成功！")
    print()

    if product["type"] == "report":
        # 报告类: 显示 .md 内容摘要
        content = post_resp.text
        lines = content.split("\n")
        print(f"  报告总长度: {len(content)} 字符, {len(lines)} 行")
        print()
        print("--- 报告前 30 行 ---")
        for line in lines[:30]:
            print(f"  {line}")
        if len(lines) > 30:
            print(f"  ... (共 {len(lines)} 行，已截断)")
        print("--- 报告结束 ---")
    else:
        # API 类: 显示 JSON 数据
        try:
            data = post_resp.json()
            data_str = json.dumps(data, indent=2, ensure_ascii=False)
            if len(data_str) > 800:
                print(data_str[:800])
                print(f"  ... (共 {len(data_str)} 字符，已截断)")
            else:
                print(data_str)
        except Exception:
            print(post_resp.text[:800])

    print()
    print(f"[链上验证] https://basescan.org/address/{pay_to}")

elif post_resp.status_code == 402:
    print("[FAIL] 支付被拒 (402)")
    try:
        print(json.dumps(post_resp.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(post_resp.text[:500])

elif post_resp.status_code == 502:
    print("[FAIL] 结算失败 (502)")
    try:
        print(json.dumps(post_resp.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(post_resp.text[:500])

else:
    print(f"[FAIL] 意外状态码: {post_resp.status_code}")
    try:
        print(json.dumps(post_resp.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(post_resp.text[:500])

print()
print("[查看日志] Get-Content F:\\afie_proxy\\logs\\stderr.log -Tail 20")
