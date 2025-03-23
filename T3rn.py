# 导入 Web3 库
from web3 import Web3
from eth_account import Account
import time
import os
import random  
import traceback
from datetime import datetime

# 数据桥接配置
from data_bridge import data_bridge
from keys_and_addresses import private_keys, labels
from network_config import networks

def center_text(text):
    terminal_width = os.get_terminal_size().columns
    lines = text.splitlines()
    return "\n".join(line.center(terminal_width) for line in lines)

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

description = """
T3RN自动桥接交互   ---V2 
X:@caitoudu    菜头是好人
"""

chain_symbols = {
    'Base': '\033[34m',
    'OP Sepolia': '\033[91m',         
}

green_color = '\033[92m'
reset_color = '\033[0m'
error_color = '\033[91m'
warning_color = '\033[93m'

explorer_urls = {
    'Base': 'https://sepolia.base.org', 
    'OP Sepolia': 'https://sepolia-optimism.etherscan.io/tx/',
    'b2n': 'https://b2n.explorer.caldera.xyz/tx/'
}

class AddressState:
    def __init__(self, private_keys, initial_network='Base'):
        self.address_states = {}
        self.tx_history = {}
        
        for priv_key in private_keys:
            account = Account.from_key(priv_key)
            address = account.address
            self.address_states[address] = {
                'current_network': initial_network,
                'alternate_network': 'OP Sepolia' if initial_network == 'Base' else 'Base',
                'last_tx_time': None
            }

    def get_network(self, address):
        return self.address_states[address]['current_network']
    
    def switch_network(self, address):
        current = self.address_states[address]['current_network']
        alternate = self.address_states[address]['alternate_network']
        self.address_states[address]['current_network'] = alternate
        self.address_states[address]['alternate_network'] = current
        return alternate
    
    def record_transaction(self, address, tx_hash):
        self.tx_history.setdefault(address, []).append({
            'tx_hash': tx_hash,
            'timestamp': datetime.now().timestamp()
        })
    
    def check_cooldown(self, address, cooldown=600):
        last_tx = self.address_states[address].get('last_tx_time')
        if last_tx and (datetime.now().timestamp() - last_tx) < cooldown:
            remaining = cooldown - (datetime.now().timestamp() - last_tx)
            print(f"{warning_color}⚠️ 冷却中: 请等待 {int(remaining)} 秒后重试{reset_color}")
            return True
        return False

def get_b2n_balance(web3, my_address):
    try:
        return web3.from_wei(web3.eth.get_balance(my_address), 'ether')
    except Exception as e:
        print(f"{error_color}获取b2n余额错误: {e}{reset_color}")
        return 0

def check_balance(web3, my_address):
    try:
        return web3.from_wei(web3.eth.get_balance(my_address), 'ether')
    except Exception as e:
        print(f"{error_color}余额查询失败: {e}{reset_color}")
        return 0

def parse_revert_reason(error):
    """解析智能合约 revert 原因"""
    try:
        hex_str = str(error).split('0x08c379a0')[-1][:64]
        return bytes.fromhex(hex_str).decode('utf-8', errors='ignore').strip('\x00')
    except:
        return "未知错误原因"

def send_bridge_transaction(web3, account, my_address, data, network_name, address_state):
    try:
        if address_state.check_cooldown(my_address):
            return None, None

        # 验证交易金额
        value_in_ether = 0.301
        if not (0.300 <= value_in_ether <= 0.302):
            raise ValueError(f"无效金额: {value_in_ether} ETH (必须为0.301±0.001)")

        value_in_wei = web3.to_wei(value_in_ether, 'ether')
        
        # 获取 nonce
        nonce = web3.eth.get_transaction_count(my_address, 'pending')
        
        # Gas 估算
        gas_estimate = web3.eth.estimate_gas({
            'to': networks[network_name]['contract_address'],
            'from': my_address,
            'data': data,
            'value': value_in_wei
        })
        gas_limit = int(gas_estimate * 1.5)  # 增加50%安全边际
        
        # 动态 Gas 价格
        base_fee = web3.eth.get_block('latest')['baseFeePerGas']
        priority_fee = web3.to_wei(7, 'gwei')  # 提高优先级费用
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

        # 签名交易
        signed_txn = web3.eth.account.sign_transaction(transaction, account.key)
        
        # 发送交易
        tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        # 记录交易时间
        address_state.address_states[my_address]['last_tx_time'] = datetime.now().timestamp()
        address_state.record_transaction(my_address, tx_hash.hex())

        # 显示交易详情
        balance = check_balance(web3, my_address)
        explorer_link = f"{explorer_urls[network_name]}{tx_hash.hex()}"

        print(f"{green_color}📤 发送地址: {account.address}")
        print(f"⛽ 使用Gas: {tx_receipt['gasUsed']}")
        print(f"🗳️  区块号: {tx_receipt['blockNumber']}")
        print(f"💰 ETH余额: {balance:.5f} ETH")

        # 查询b2n余额
        try:
            b2n_web3 = Web3(Web3.HTTPProvider('https://b2n.rpc.caldera.xyz/http'))
            if b2n_web3.is_connected():
                b2n_balance = get_b2n_balance(b2n_web3, my_address)
                print(f"🔵 b2n余额: {b2n_balance:.4f} b2n")
        except Exception as e:
            print(f"{error_color}🔴 b2n查询失败: {str(e)[:50]}{reset_color}")

        print(f"🔗 区块浏览器链接: {explorer_link}\n{reset_color}")

        return tx_hash.hex(), value_in_ether

    except ValueError as ve:
        print(f"{error_color}参数错误: {ve}{reset_color}")
        return None, None
    except Exception as e:
        error_msg = str(e)
        if 'execution reverted' in error_msg:
            reason = parse_revert_reason(error_msg)
            print(f"{error_color}合约拒绝交易: {reason}{reset_color}")
        else:
            print(f"{error_color}交易失败: {error_msg[:100]}{reset_color}")
        return None, None

def modify_data_address(original_data, current_address, bridge_type):
    current_address_clean = current_address.lower().replace("0x", "")
    
    # 修正后的地址偏移位置
    address_positions = {
        "Base - OP Sepolia": 298,
        "OP - Base": 298
    }
    
    start = address_positions.get(bridge_type, 298)
    new_address_part = "000000000000000000000000" + current_address_clean
    
    if len(new_address_part) != 64:
        raise ValueError("地址格式错误")
    
    return original_data[:start] + new_address_part + original_data[start+64:]

def process_network_transactions(network_name, bridges, chain_data, successful_txs, address_state):
    # 网络连接重试逻辑
    web3 = None
    for _ in range(3):
        try:
            web3 = Web3(Web3.HTTPProvider(chain_data['rpc_url']))
            if web3.is_connected():
                break
        except:
            time.sleep(2)
    
    if not web3 or not web3.is_connected():
        print(f"{error_color}无法连接到 {network_name}{reset_color}")
        return successful_txs

    num_addresses = len(private_keys)
    for bridge in bridges:
        for i, private_key in enumerate(private_keys):
            account = Account.from_key(private_key)
            my_address = account.address
            print(f"\n{chain_symbols[network_name]}🔁 处理地址 {i+1}/{num_addresses} ({my_address[:6]}...){reset_color}")

            original_data = data_bridge.get(bridge)
            if not original_data:
                print(f"{error_color}缺少桥接数据: {bridge}{reset_color}")
                continue

            try:
                modified_data = modify_data_address(original_data, my_address, bridge)
            except ValueError as ve:
                print(f"{error_color}数据构造失败: {ve}{reset_color}")
                continue

            tx_hash, value_sent = send_bridge_transaction(web3, account, my_address, modified_data, network_name, address_state)
            
            if tx_hash:
                successful_txs += 1
                print(f"{chain_symbols[network_name]}🚀 成功交易: 总数 {successful_txs} | {labels[i]} | 金额 {value_sent:.5f} ETH{reset_color}")
            
            time.sleep(random.uniform(5, 8))  # 增加地址间间隔
    
    return successful_txs

def main():
    try:
        print("\033[92m" + center_text(description) + "\033[0m")
        print("\n\n")

        successful_txs = 0
        level = 1
        address_state = AddressState(private_keys)

        while True:
            for i, private_key in enumerate(private_keys):
                account = Account.from_key(private_key)
                my_address = account.address

                current_network = address_state.get_network(my_address)
                alternate_network = address_state.address_states[my_address]['alternate_network']

                # 网络连接检查
                web3 = None
                for _ in range(3):
                    try:
                        web3 = Web3(Web3.HTTPProvider(networks[current_network]['rpc_url']))
                        if web3.is_connected():
                            break
                    except:
                        time.sleep(2)
                
                if not web3 or not web3.is_connected():
                    print(f"{error_color}网络连接失败，切换至 {alternate_network}{reset_color}")
                    address_state.switch_network(my_address)
                    current_network = alternate_network
                    web3 = Web3(Web3.HTTPProvider(networks[current_network]['rpc_url']))

                # 余额检查
                balance = check_balance(web3, my_address)
                if balance < 0.31:
                    print(f"{chain_symbols[current_network]}余额不足 {balance:.3f} ETH，切换至 {alternate_network}{reset_color}")
                    new_network = address_state.switch_network(my_address)
                    current_network = new_network
                    web3 = Web3(Web3.HTTPProvider(networks[current_network]['rpc_url']))

                bridges = ["Base - OP Sepolia"] if current_network == 'Base' else ["OP - Base"]
                successful_txs = process_network_transactions(
                    current_network, 
                    bridges, 
                    networks[current_network], 
                    successful_txs,
                    address_state
                )

                wait_time = random.uniform(60, 90)  # 增加轮次间间隔
                print(f"\n{chain_symbols[current_network]}⏳ 第{level}轮完成，等待 {wait_time:.1f} 秒{reset_color}")
                time.sleep(wait_time)
                level += 1

    except KeyboardInterrupt:
        print(f"\n{warning_color}🛑 用户中断操作，程序退出{reset_color}")
    except Exception as e:
        print(f"\n{error_color}⚠️ 严重错误: {str(e)}{reset_color}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
