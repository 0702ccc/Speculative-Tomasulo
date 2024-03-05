# cpu.py
from new_cpu import *
import os


def parse_instruction(line):
    """
   将输入的指令行解析为指令对象。

   Input:
   - line (str): 输入的指令行

   Output:
   - Instruction: 解析得到的指令对象
   """
    fields = line.split()
    opcode = fields[0]
    dest = fields[1]
    src1 = fields[2][:-1] if fields[2][-1] == '+' else fields[2]  # 如果有尾随的 "+"，则去除它
    src2 = fields[3]
    return Instruction(opcode, dest, src1, src2)


def trans(ins):
    """
    将指令对象转换为标准输出格式。

    Input:
    - ins (Instruction): 输入的指令对象

    Output:
    - str: 转换得到的标准输出格式的字符串
    """
    result = ""
    if ins.opcode == "LD":
        result = f"fld {ins.destination} {ins.src1}({ins.src2})"
    elif ins.opcode == "SD":
        result = f"fsd {ins.destination} {ins.src1}({ins.src2})"
    elif ins.opcode == "ADDD":
        result = f"fadd.d {ins.destination},{ins.src1},{ins.src2}"
    elif ins.opcode == "SUBD":
        result = f"fsub.d {ins.destination},{ins.src1},{ins.src2}"
    elif ins.opcode == "MULTD":
        result = f"fmul.d {ins.destination},{ins.src1},{ins.src2}"
    elif ins.opcode == "DIVD":
        result = f"fdid.d {ins.destination},{ins.src1},{ins.src2}"
    return result


def rs_state(rs_list):
    """
    将预约站列表的状态转换为格式化字符串。

    Input:
    - rs_list (list): 预约站对象列表

    Output:
    - str: 转换得到的格式化字符串，包含预约站的状态信息
    """
    state_result = ""
    for i, rs in enumerate(rs_list, start=1):
        if not rs.busy:
            state_result += f"{rs.name} : NO,,,,,,;\n"
            continue
        state = "Yes" if rs.busy else "No"
        op = rs.op if rs.op else ""
        vj = str(rs.vj) if rs.vj not in {0, None} else ""
        if vj and not vj.startswith("#"):
            if op == "LD":
                vj = f"Regs[R{vj}]"
            else:
                vj = f"Regs[F{vj}]"
        vk = str(rs.vk) if rs.vk not in {0, None} else ""
        if vk and not vk.startswith("#"):
            if op == "LD":
                vk = f"Regs[R{vk}]"
            else:
                vk = f"Regs[F{vk}]"
        qj = f"#{str(rs.qj)}" if rs.qj not in {0, None} else ""
        qk = f"#{str(rs.qk)}" if rs.qk not in {0, None} else ""
        rob_index = rs.rob_index if rs.rob_index else ""
        a = rs.a if rs.a else ""
        state_result += f"{rs.name} : {state}, {op}, {vj}, {vk}, {qj}, {qk}, #{rob_index};\n"
    return state_result


class CPU:
    def __init__(self, num_registers, memory_size, num_load_buffers, num_rob_entries,
                 instruction_queue):
        self.bus = Bus()  # 创建总线
        self.rob_bus = Bus()  # 创建rob使用的数据bus
        self.register_group = RegisterGroup(num_registers, rob_bus=self.rob_bus)  # 创建寄存器组
        self.memory = Memory(memory_size, bus=self.bus, num_load_buffers=num_load_buffers)  # 创建内存
        self.fp_add = FPUnit(unit_type="Add", num_reservation_stations=3, execution_cycles={
            "ADDD": 2, "SUBD": 2
        }, bus=self.bus)  # 创建浮点数执行单元
        self.fp_multd = FPUnit(unit_type="Mult", num_reservation_stations=2, execution_cycles={
            "MULTD": 10, "DIVD": 20
        }, bus=self.bus)
        self.reorder_buffer = ReorderBuffer(num_rob_entries, bus=self.bus, rob_bus=self.rob_bus)
        self.clock_cycles = 0  # 初始化时钟周期计数
        self.instruction_queue = instruction_queue  # 设置初始指令队列

    def run_simulation(self):
        """
        模拟CPU运行,运行时会输出各个周期的状态。

        输入:
        - self: 模拟器对象

        输出:
        - 无
        """
        with open(output_file, 'w') as output:
            # 用于判断前后两个周期是否输出相同的状态
            pre_state = ""

            # 用于计数相同状态的连续周期数
            same_counter = 0

            while True:
                self.clock_cycles += 1  # 模拟时钟周期开始
                print(f"clock Cycle：{self.clock_cycles}")

                self.issue_instructions()  # 阶段 1：发射指令

                self.update_components()  # 阶段 2：更新各个组件

                self.register_group.update()  # 阶段 3：模拟写回
                self.bus.update()
                self.rob_bus.update()

                new_state = self.record_component_state()  # 记录组件状态到文件，包含处理重复输出操作

                # 检查新状态是否与前一状态不同
                if new_state != pre_state:
                    if pre_state:
                        if same_counter == 0:
                            output.write(f"cycle_{self.clock_cycles - 1};\n")
                        else:
                            output.write(f"cycle_{self.clock_cycles - same_counter - 1}-{self.clock_cycles - 1};\n")
                        output.write(pre_state)
                    pre_state = new_state
                    same_counter = 0
                else:
                    same_counter += 1

                if self.are_all_components_idle():  # 检查是否所有组件都处于空闲状态，如果是，则模拟结束
                    output.write(f"cycle_{self.clock_cycles};\n")
                    output.write(pre_state)
                    print("Simulation Complete.")

                    for entry in rob_record:  # 按要求添加每条指令四个阶段代表周期
                        ins = entry.instruction
                        if entry is not None:
                            if entry.instruction.opcode == "SD":
                                output.write(
                                    f"{ins.opcode} {ins.destination} {ins.src1} {ins.src2}: {entry.state_cycle[0]},{entry.state_cycle[1]},{entry.state_cycle[2]}\n")
                            else:
                                output.write(
                                    f"{ins.opcode} {ins.destination} {ins.src1} {ins.src2}: {entry.state_cycle[0]},{entry.state_cycle[1]},{entry.state_cycle[2]},{entry.state_cycle[3]}\n")
                    break

    def issue_instructions(self):
        """
        发射指令的函数:检查指令队列是否非空，然后根据指令类型调用相应的功能单元发射指令。

        Inputs:
        - None

        Outputs:
        - bool: 指示指令是否成功发射的布尔值

        Raises:
        - ValueError: 当指令类型无法识别时引发异常
        """

        if self.instruction_queue:  # 检查指令队列是否非空
            instruction = self.instruction_queue[0]
            # 检查指令是否可以发射
            sd_vj, sd_qj = self.register_group.read(instruction.destination)
            rob_index = self.reorder_buffer.issue_instruction(instruction, self.clock_cycles, sd_vj, sd_qj)

            if not rob_index:  # 没有空闲ROB时，发射失败
                return False
            # 根据指令类型调用相应的功能单元
            if instruction.opcode in {"ADDD", "SUBD"}:
                vj, qj = self.register_group.read(instruction.src1)
                vk, qk = self.register_group.read(instruction.src2)
                if self.fp_add.issue_instruction(instruction, vj, vk, qj, qk, rob_index):
                    self.instruction_queue.pop(0)
                    self.register_group.write(instruction.destination, rob_index)
                else:
                    self.reorder_buffer.clear_rob()
            elif instruction.opcode in {"MULTD", "DIVD"}:
                vj, qj = self.register_group.read(instruction.src1)
                vk, qk = self.register_group.read(instruction.src2)
                if self.fp_multd.issue_instruction(instruction, vj, vk, qj, qk, rob_index):
                    self.instruction_queue.pop(0)
                    self.register_group.write(instruction.destination, rob_index)
                else:
                    self.reorder_buffer.clear_rob()
            elif instruction.opcode == "LD":
                vj, qj = self.register_group.read(instruction.src2)
                if self.memory.issue_instruction(instruction, vj, qj, rob_index):
                    self.instruction_queue.pop(0)
                    self.register_group.write(instruction.destination, rob_index)
                else:
                    self.reorder_buffer.clear_rob()
            elif instruction.opcode == "SD":
                self.instruction_queue.pop(0)
                return
            else:
                raise ValueError(f"Error Instruction!")


    def update_components(self):  # 更新各个组件
        """
        调用各个功能部件的更新函数

        Inputs:
        - None

        Outputs:
        - None
        """
        # 优化功能
        # dest = self.reorder_buffer.get_dest()
        # self.memory.update(dest)
        self.memory.update(0)
        self.fp_add.update()
        self.fp_multd.update()
        self.reorder_buffer.update(self.clock_cycles)
        self.register_group.update()

    def record_component_state(self):
        """
            记录Speculative Tomasulo模拟器中各个组件的状态。

            Input:
            - None。

            Output:
            - str: 包含不同组件状态信息的格式化字符串。
        """
        state_result = ""  # 将各个组件的状态记录到字符串变量
        # 添加ROB状态
        rob_size = self.reorder_buffer.size
        new_head = (self.reorder_buffer.tail + 1) % rob_size
        for i in range(0, rob_size - 1):
            if self.reorder_buffer.entries[new_head] is None:
                new_head = (new_head + 1) % rob_size
        for i in range(0, rob_size - 1):
            index = (new_head + i) % rob_size  # 计算在循环队列中的实际索引
            current_entry = self.reorder_buffer.entries[index]
            if current_entry is not None:
                state = "Yes" if current_entry.busy else "No"
                instruction_state = trans(current_entry.instruction)
                en_state = current_entry.state if current_entry.state else ""
                dest = current_entry.destination if current_entry.instruction else ""
                value = current_entry.value if current_entry.instruction else ""
                state_result += f"entry{i + 1} : {state}, {instruction_state}, {en_state}, {dest}, {value};\n"
            else:
                state_result += f"entry{i + 1} :No,,,,;\n"
        # 添加Reservation Stations状态 Load Add MULT
        state_result += rs_state(self.memory.load_buffers)
        state_result += rs_state(self.fp_add.reservation_stations)
        state_result += rs_state(self.fp_multd.reservation_stations)
        # 添加register状态
        reg_reorder = "Reorder:"
        reg_busy = "Busy:"
        for i, reg in enumerate(self.register_group.registers):
            if reg.busy:
                reg_reorder += f"F{i}: {reg.rob_label};"
                reg_busy += f"F{i}:Yes;"
            else:
                reg_reorder += f"F{i}:;"
                reg_busy += f"F{i}:No;"
        state_result += reg_reorder + "\n"
        state_result += reg_busy + "\n"
        state_result += "------------------------------------------\n"
        # 一次性写入文件
        return state_result

    def are_all_components_idle(self):
        if not self.fp_add.finish():
            return False
        if not self.fp_multd.finish():
            return False
        if not self.memory.finish():
            return False
        if not self.reorder_buffer.finish():
            return False
        return True


if __name__ == "__main__":
    # 获取上级目录
    parent_dir = os.path.abspath(os.path.join(os.getcwd(), os.pardir))
    # 构建输入和输出文件的完整路径
    input_file = os.path.join(parent_dir, 'input', 'input1.txt')
    output_file = os.path.join(parent_dir, 'output', 'output1.txt')
    # 解析输入文件中的指令并存储到指令队列
    ins_queue = []
    with open(input_file, 'r') as file:
        for line in file:  # 每一行都是一个指令
            instruction = parse_instruction(line.strip())
            ins_queue.append(instruction)
    # 初始化CPU并运行模拟器
    cpu = CPU(num_registers=11, memory_size=1024, num_load_buffers=2, num_rob_entries=6,
              instruction_queue=ins_queue)
    cpu.run_simulation()
