# 导入 Web3 库
from web3 import Web3
from eth_account import Account
import time
import sys
import os
import random  # 引入随机模块

# 数据桥接配置
from data_bridge import data_bridge
from keys_and_addresses import private_keys, labels
from network_config import networks

# 文本居中函数
def center_text(text):
    terminal_width = os.get_terminal_size().columns
    lines = text.splitlines()
    centered_lines = [line.center(terminal_width) for line in lines]
    return "\n".join(centered_lines)

# 清理终端函数
def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

description = """
T3RN--AUTOSWAP   V2
X:@caitoudu  菜头Do
"""

# 每个链的颜色和符号
chain_symbols = {
    'Base': '\033[34m',  # 更新为 Base 链的颜色
    'OP Sepolia': '\033[91m',         
}

# 颜色定义
green_color = '\033[92m'
reset_color = '\033[0m'
menu_color = '\033[95m'  # 菜单文本颜色

# 每个网络的区块浏览器URL
explorer_urls = {
    'Base': 'https://sepolia.base.org', 
    'OP Sepolia': 'https://sepolia-optimism.etherscan.io/tx/',
    'b2n': 'https://b2n.explorer.caldera.xyz/tx/'
}

# 地址管理类
class AddressState:
    def __init__(self, private_keys, initial_network='Base'):
        self.address_states = {}
        # 初始化每个地址的链状态
        for priv_key in private_keys:
            account = Account.from_key(priv_key)
            address = account.address
            self.address_states[address] = {
                'current_network': initial_network,
                'alternate_network': 'OP Sepolia' if initial_network == 'Base' else 'Base'
            }
    
    def get_network(self, address):
        return self.address_states[address]['current_network']
    
    def switch_network(self, address):
        # 切换当前链和备用链
        current = self.address_states[address]['current_network']
        alternate = self.address_states[address]['alternate_network']
        self.address_states[address]['current_network'] = alternate
        self.address_states[address]['alternate_network'] = current
        return alternate

# 获取b2n余额的函数
def get_b2n_balance(web3, my_address):
    balance = web3.eth.get_balance(my_address)
    return web3.from_wei(balance, 'ether')

# 检查链的余额函数
def check_balance(web3, my_address):
    balance = web3.eth.get_balance(my_address)
    return web3.from_wei(balance, 'ether')

# 创建和发送交易的函数
def send_bridge_transaction(web3, account, my_address, data, network_name):
    nonce = web3.eth.get_transaction_count(my_address, 'pending')
    value_in_ether = 0.301
    value_in_wei = web3.to_wei(value_in_ether, 'ether')

    try:
        gas_estimate = web3.eth.estimate_gas({
            'to': networks[network_name]['contract_address'],
            'from': my_address,
            'data': data,
            'value': value_in_wei
        })
        gas_limit = gas_estimate + 50000  # 增加安全边际
    except Exception as e:
        print(f"估计gas错误: {e}")
        return None, None

    base_fee = web3.eth.get_block('latest')['baseFeePerGas']
    priority_fee = web3.to_wei(5, 'gwei')
    max_fee = base_fee + priority_fee

    transaction = {
        'nonce': nonce,
        'to': networks[network_name]['contract_address'],
        'value': value_in_wei,
        'gas': gas_limit,
        'maxFeePerGas': max_fee,
        'maxPriorityFeePerGas': priority_fee,
        'chainId': networks[network_name]['chain_id'],
        'data': data
    }

    try:
        signed_txn = Account.sign_transaction(transaction, account.key)
    except Exception as e:
        print(f"签名交易错误: {e}")
        return None, None

    try:
        tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        # 获取最新余额
        balance = web3.eth.get_balance(my_address)
        formatted_balance = web3.from_wei(balance, 'ether')

        # 获取区块浏览器链接
        explorer_link = f"{explorer_urls[network_name]}{tx_hash.hex()}"

        # 显示交易信息
        print(f"{green_color}📤 发送地址: {account.address}")
        print(f"⛽ 使用Gas: {tx_receipt['gasUsed']}")
        print(f"🗳️  区块号: {tx_receipt['blockNumber']}")
        print(f"💰 ETH余额: {formatted_balance} ETH")
        b2n_balance = get_b2n_balance(Web3(Web3.HTTPProvider('https://b2n.rpc.caldera.xyz/http')), my_address)
        print(f"🔵 b2n余额: {b2n_balance} b2n")
        print(f"🔗 区块浏览器链接: {explorer_link}\n{reset_color}")

        return tx_hash.hex(), value_in_ether
    except Exception as e:
        print(f"发送交易错误: {e}")
        return None, None

# 新增：多地址时自动 动态替换data结构中的地址部分
def replace_middle_address(original_data, current_address):
    """
    替换 data 中第 163 列到第 202 列的地址字段
    Args:
        original_data (str): 原始 data 字符串
        current_address (str): 当前钱包地址（带0x）
    Returns:
        str: 替换后的 data
    """
    # 去掉 0x 前缀并转为小写
    current_address_clean = current_address.lower().replace("0x", "")
    
    # 定义替换范围（列号从 0 开始）
    start = 162  # 第 163 列（Python 索引从 0 开始）
    end = 202    # 第 202 列（包含）
    
    
    # 生成新地址段（固定40字符）
    if len(current_address_clean) != 40:
        raise ValueError(f"地址长度应为40字符，实际 {len(current_address_clean)}")
    
    # 替换指定区间
    modified_data = original_data[:start] + current_address_clean + original_data[end:]
    
    return modified_data

# 逐个地址处理交易
def process_single_address_transaction(web3, account, network_name, bridge, successful_txs):
    my_address = account.address
    print(f"正在处理地址: {my_address}")

    # 获取 data
    original_data = data_bridge.get(bridge)
    if not original_data:
        print(f"桥接 {bridge} 数据不可用!")
        return successful_txs

    try:
        # 动态替换 data 地址部分
        modified_data = replace_middle_address(original_data, my_address)
    except ValueError as e:
        print(f"地址替换错误: {e}")
        return successful_txs

    # 发送交易
    tx_hash, value_sent = send_bridge_transaction(web3, account, my_address, modified_data, network_name)
    if tx_hash:
        successful_txs += 1
        print(f"{chain_symbols[network_name]}🚀 成功交易总数: {successful_txs} | 桥接: {bridge} | 金额: {value_sent:.5f} ETH ✅{reset_color}\n")

    # 交易间短延时
    wait_time = random.uniform(0.8, 1)
    time.sleep(wait_time)
    return successful_txs

def main():
    print("\033[92m" + center_text(description) + "\033[0m")
    print("\n\n")

    successful_txs = 0
    level = 1
    address_state = AddressState(private_keys, initial_network='Base')  # 初始化地址状态

    while True:
        # 遍历每个地址并完全独立处理
        for i, private_key in enumerate(private_keys):
            account = Account.from_key(private_key)
            my_address = account.address
            label = labels[i]

            # 获取当前地址的网络状态
            current_network = address_state.get_network(my_address)
            alternate_network = address_state.address_states[my_address]['alternate_network']

            # 连接到当前网络
            web3 = Web3(Web3.HTTPProvider(networks[current_network]['rpc_url']))
            while not web3.is_connected():
                print(f"地址 {my_address} 无法连接到 {current_network}，正在尝试重新连接...")
                time.sleep(5)
                web3 = Web3(Web3.HTTPProvider(networks[current_network]['rpc_url']))

            # 检查当前网络余额是否足够
            balance = check_balance(web3, my_address)
            if balance < 0.301:
                print(f"{chain_symbols[current_network]}⚠️ {my_address} 在 {current_network} 余额不足 0.301 ETH，尝试切换到 {alternate_network}{reset_color}")

                # 检查目标网络余额
                alt_web3 = Web3(Web3.HTTPProvider(networks[alternate_network]['rpc_url']))
                alt_balance = check_balance(alt_web3, my_address)
                if alt_balance >= 0.301:
                    new_network = address_state.switch_network(my_address)
                    current_network = new_network
                    web3 = alt_web3
                    print(f"🔄 已切换到 {new_network}，余额充足")
                else:
                    print(f"❌ 两个网络余额均不足，跳过地址 {my_address}")
                    continue

            # 处理当前地址的交易
            bridge_name = "Base - OP Sepolia" if current_network == 'Base' else "OP - Base"
            successful_txs = process_single_address_transaction(
                web3, account, current_network, bridge_name, successful_txs
            )

        # 地址间延时
        wait_time = random.uniform(1, 2)
        print(f"⏳ 第{level}轮完成，等待 {wait_time:.2f} 秒...\n")
        level += 1
        time.sleep(wait_time)

if __name__ == "__main__":
    main()
