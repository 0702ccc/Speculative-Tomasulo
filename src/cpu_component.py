# components.py
rob_record = []


class Instruction:
    def __init__(self, opcode, destination, src1, src2):
        """
        指令类：包含指令的操作数、原地址、目标地址
        """
        self.opcode = opcode
        self.destination = destination
        self.src1 = src1
        self.src2 = src2


class ReorderBufferEntry:
    def __init__(self, rob_index, instruction):
        """
        ROB条目类：包含一个ROB条目的各个属性，如busy、state等等
        """
        self.busy = True
        self.instruction = instruction
        self.state = None
        self.destination = None
        self.value = None
        self.rob_index = rob_index
        self.sd_data = {"vj": None, "qj": None}
        self.state_cycle = []
        self.issue_this_cycle = False


class ReorderBuffer:
    def __init__(self, size, bus, rob_bus):
        """
        ROB组：使用循环队列实现多条ROB条目的
        属性：
            size：大小
            bus：总线
            rob_bus：rob与存储器传输数据的线
        """
        self.size = size + 1  # 多一个位置实现循环队列
        self.entries = [None] * (size + 1)
        self.head = 0
        self.new_head = 0
        self.tail = 0
        self.rob_index_counter = 0
        self.bus = bus
        self.rob_bus = rob_bus

    def issue_instruction(self, instruction, clock_cycle, vj, qj):
        """
        尝试发射指令并将新的ROB条目加入ROB缓冲区。

        Args:
        - instruction (Instruction): 待发射的指令对象
        - clock_cycle (int): 当前时钟周期
        - vj: 源操作数1的值
        - qj: 源操作数1的状态（是否准备好）

        Returns:
        - int or None: 如果成功发射，返回新ROB条目的索引；如果发射失败，返回None
        """
        self.rob_index_counter += 1  # 创建一个新的ROB条目
        rob_entry = ReorderBufferEntry(self.rob_index_counter, instruction)

        next_tail = (self.tail + 1) % self.size  # 尝试将ROB条目加入ROB缓冲区
        if next_tail != self.head:  # 如果缓冲区未满，加入ROB条目
            self.entries[self.tail] = rob_entry
            self.tail = next_tail
            rob_entry.state = "Issue"
            rob_entry.issue_this_cycle = True
            rob_entry.state_cycle.append(clock_cycle)
            if rob_entry.instruction.opcode == "SD":
                rob_entry.destination = None
                rob_entry.sd_data["vj"] = vj
                rob_entry.sd_data["qj"] = qj
            else:
                rob_entry.destination = instruction.destination
            # 返回ROB条目的索引
            return rob_entry.rob_index
        else:  # 如果缓冲区已满，发射指令失败
            self.rob_index_counter -= 1
            print(clock_cycle, "ROB is full. Unable to issue instruction.")
            return None

    def update(self, clock_cycle):
        """
        更新ROB缓冲区中的条目状态。

        Args:
        - clock_cycle (int): 当前时钟周期

        Returns:
        - None
        """
        label, data = self.bus.read()
        exec_list = self.bus.exec  # 检查总线上是否有新数据
        index = self.head
        # 根据不同条件，更新ROB的四个状态
        while index != self.tail:
            entry = self.entries[index]
            if entry.instruction.opcode == "SD":
                self.update_sd(label, data, index, clock_cycle)
                index = (index + 1) % self.size
                continue
            if entry.state == "Issue" and entry.rob_index in exec_list:
                entry.state = "Exec"
            if index == self.head:
                if entry.state == "Write result":
                    entry.busy = False
                    entry.state = "Commit"
                    self.new_head = (self.head + 1) % self.size
                    entry.state_cycle.append(clock_cycle)
                    rob_record.append(entry)
            if label and entry.rob_index == label:  # 使用接收到的数据更新条目
                entry.value = data
                entry.state = "Write result"  # 尝试写寄存器
                entry.state_cycle.append(clock_cycle - 1)
                entry.state_cycle.append(clock_cycle)
                self.rob_bus.write(entry.instruction.destination, entry.rob_index)
            index = (index + 1) % self.size
        self.head = self.new_head

    def update_sd(self, label, data, index, clock_cycle):
        """
        更新SD指令的ROB条目状态。

        Args:
        - label: 总线上的标签
        - data: 总线上的数据
        - index: ROB中的索引
        - clock_cycle: 当前时钟周期

        Returns:
        - None
        """
        entry = self.entries[index]
        if entry.sd_data["qj"]:
            if entry.sd_data["qj"] == label:
                entry.sd_data["vj"] = f"#{label}"
                entry.sd_data["qj"] = None
        if entry.state == "Issue":
            if entry.issue_this_cycle:
                entry.issue_this_cycle = False
            else:
                entry.state = "Exec"
                entry.destination = f"Mem[{entry.instruction.src1}+{entry.instruction.src2}]"
            return
        if index == self.head and entry.state == "Exec" and entry.sd_data["vj"]:
            entry.state = "Commit"
            entry.busy = False
            self.new_head = (self.head + 1) % self.size
            entry.state_cycle.append(clock_cycle - 1)
            entry.state_cycle.append(clock_cycle)
            rob_record.append(entry)
        return

    # 当没有rs的时候需要回滚rob
    def clear_rob(self):
        """
        当没有RS的时候需要回滚ROB。

        Returns:
        - None
        """
        self.rob_index_counter -= 1
        if self.tail == 0:
            self.tail = self.size - 1
        else:
            self.tail -= 1
        self.entries[self.tail] = None

    def finish(self):
        """
        检查浮点数执行单元中的所有保留站是否都已完成。

        Returns:
        - bool: 如果所有保留站都已完成，返回True；否则返回False
        """
        for entry in self.entries:
            if entry and entry.busy:
                return False
        return True

    # 优化功能

    # def clear_entries(self):
    #     """
    #     当分支条件判断错误时，清除 ROB 中的所有条目。
    #
    #     Returns:
    #     - None
    #     """
    #     self.head = 0
    #     self.new_head = 0
    #     self.tail = 0
    #     self.rob_index_counter = 0
    #     self.entries = [None] * self.size

    # def get_dest(self):
    #     """
    #     返回当前ROB条目中的目的地址列表，用于向CPU传递信息。
    #
    #     Returns:
    #     - dest
    #     """
    #     dest = []
    #     for entry in self.entries:
    #         if entry and entry.busy:
    #             dest.append(entry.destination)
    #     return dest


class Bus:
    def __init__(self):
        """
        总线类，用于在执行单元之间传递数据和标签。

        Attributes:
        - label (str): 当前总线上的标签
        - value (str): 当前总线上的数据
        - new_label (str): 新的标签，用于写入总线
        - new_value (str): 新的数据，用于写入总线
        - exec (list): 执行单元中的执行列表
        """
        self.label = ""
        self.value = ""
        self.new_label = ""
        self.new_value = ""
        self.exec = []

    def read(self):
        """
        读取总线上的数据和标签。

        Returns:
        - tuple: 包含当前总线上的标签和数据的元组
        """
        return (self.label, self.value)

    def write(self, label, data):
        """
        向总线上写入数据。

        Args:
        - label (str): 待写入的标签
        - data (str): 待写入的数据

        Returns:
        - bool: 如果成功写入，返回True；否则返回False
        """
        if not self.new_label:
            self.new_value = data
            self.new_label = label
            return True
        else:
            return False

    def update(self):
        """
        更新总线状态。

        Returns:
        - None
        """
        if self.new_label:
            self.value = self.new_value
            self.label = self.new_label
            self.new_value = ""
            self.new_label = ""
        else:
            self.value = ""
            self.label = ""
        self.exec = []


class Register:
    def __init__(self, rob_label=None, busy=False, data=0):
        """
        寄存器类，用于表示一个通用寄存器。

        Args:
        - rob_label (int): ROB标签，指示寄存器的更新状态
        - busy (bool): 寄存器是否被占用
        - data: 寄存器中存储的数据
        """
        self.busy = busy
        self.rob_label = rob_label
        self.data = data


class RegisterGroup:
    def __init__(self, num_registers, rob_bus=None):
        """
        寄存器组类，用于管理通用寄存器和基址寄存器。

        Args:
        - num_registers (int): 寄存器数量
        - rob_bus: 与ROB通信的总线对象
        """
        self.registers = [Register() for _ in range(num_registers)]  # 使用 Register 类创建每个寄存器对象
        self.rob_bus = rob_bus

    def read(self, res):
        """
        从寄存器组中读取数据。

        Args:
        - res (str): 待读取的寄存器标识符

        Returns:
        - tuple: 包含vj和qj（如果有）的元组
        """
        reg, value = self.rob_bus.read()
        if res == reg:
            return f"#{value}", None
        # 若是通用寄存器
        if res[0] in {'F'} and res[1:].isdigit():
            register_index = int(res[1:])
            data = self.registers[register_index].data  # 从寄存器读取数据 返回vj,qj(vk,qk)
            if self.registers[register_index].busy:
                label = self.registers[register_index].rob_label
                return None, label
            else:
                return register_index, None
        # 若是基址寄存器 默认数据直接存在并返回
        elif res[0] in {'R'} and res[1:].isdigit():
            register_index = int(res[1:])
            return register_index, None
        else:
            raise ValueError("Invalid format. The input should be in the format 'F OR R+数字'")

    def write(self, res, label):
        """
        向寄存器中写入标签。

        Args:
        - res (str): 待写入的寄存器标识符
        - label (int): 待写入的标签

        Returns:
        - None
        """
        # 向寄存器中写入标签
        if res[0] in {'F', 'R'} and res[1:].isdigit():
            register_index = int(res[1:])
            self.registers[register_index].busy = True
            self.registers[register_index].rob_label = label
        else:
            raise ValueError("Invalid format. The input should be in the format 'F OR R+数字'")

    def update(self):
        """
        在时钟周期中执行的操作，读取ROB数据。

        Returns:
        - None
        """
        reg, rob_result = self.rob_bus.read()
        if rob_result:
            # 处理从总线读取的数据，若能更新则进行更新
            if reg[0] in {'F', 'R'} and reg[1:].isdigit():
                register_index = int(reg[1:])
                self.registers[register_index].busy = False
                self.registers[register_index].rob_label = None
                self.registers[register_index].data = rob_result
            else:
                raise ValueError("Invalid format. The input should be in the format 'F OR R+数字'")


class ReservationStation:
    def __init__(self, name, rob_index=None):
        """
        保留站类，用于执行浮点数运算。

        Args:
        - name (str): 保留站名称
        - rob_index (int): 与ROB相关联的索引
        - 等等
        """
        self.name = name
        self.busy = False
        self.op = None
        self.vj = None
        self.vk = None
        self.qj = None
        self.qk = None
        self.dest = None
        self.a = None
        self.remain_time = -1
        self.rob_index = rob_index
        self.issue_this_cycle = False


class Memory:
    def __init__(self, size, bus=None, num_load_buffers=1):
        """
        内存单元类，用于模拟内存的读写操作。

        Args:
        - size (int): 内存大小
        - bus: 与总线通信的总线对象
        - num_load_buffers (int): Load Buffer 的数量
        """
        self.size = size
        self.data = [0] * size
        self.bus = bus
        self.load_buffers = [ReservationStation(name=f"Load{i + 1}") for i in range(num_load_buffers)]

    def get_free_buffer(self):
        """
        获取空闲的 Load Buffer。

        Returns:
        - ReservationStation: 空闲的 Load Buffer，如果没有则返回None
        """
        for buffer in self.load_buffers:
            if not buffer.busy:
                return buffer
        return None

    def issue_instruction(self, instruction, vj, qj, rob_index):
        """
        发射指令到内存单元。

        Args:
        - instruction: 待发射的指令
        - vj: 指令操作数vj
        - qj: 指令操作数qj
        - rob_index (int): 与ROB相关联的索引

        Returns:
        - bool: 如果成功发射指令，返回True；否则返回False
        """
        # 在这里实现指令发射逻辑
        if instruction.opcode == "LD":
            buffer = self.get_free_buffer()
            if buffer:
                buffer.busy = True
                buffer.rob_index = rob_index
                buffer.op = instruction.opcode
                buffer.dest = instruction.destination
                buffer.a = instruction.src1
                buffer.vj = vj
                buffer.qj = qj
                buffer.issue_this_cycle = True
                buffer.remain_time = 2
                return True
            else:
                print("Load Buffer is full.")
                return False
        else:
            print("Unsupported instruction.")
            return False

    def update(self, dest):
        """
        在时钟周期中执行的操作，读取总线上的数据并更新 Load Buffer 状态。

        Returns:
        - None
        """
        # 读取总线上的数据
        label, data = self.bus.read()

        # 对 Load Buffer 进行更新操作，根据不同状态修改RS保留站中属性
        for buffer in self.load_buffers:
            if buffer.busy:
                if buffer.issue_this_cycle:
                    buffer.issue_this_cycle = False
                    continue
                if buffer.remain_time == 2:
                    if buffer.vj:
                        buffer.a = f"{buffer.a}+Regs[R{buffer.vj}]"
                        buffer.remain_time -= 1
                        self.bus.exec.append(buffer.rob_index)
                    else:
                        if buffer.qj == label:
                            buffer.vj = f"#{label}"
                            buffer.qj = 0
                elif buffer.remain_time == 1:
                    # if buffer.a in dest:
                    #     continue
                    buffer.remain_time -= 1
                    data = f"Mem[{buffer.a}]"
                    self.bus.write(buffer.rob_index, data)
                else:
                    buffer.busy = False

    def finish(self):
        """
        检查 Load Buffer 中的所有保留站是否都已完成。

        Returns:
        - bool: 如果所有保留站都已完成，返回True；否则返回False
        """
        for rs in self.load_buffers:
            if rs.busy:
                return False
        return True

    def read(self, address):
        """
        模拟从内存中读取数据。

        Args:
        - address (int): 内存地址

        Returns:
        - int: 从内存中读取的数据
        """
        return self.data[address]

    def write(self, address, value):
        """
        模拟向内存中写入数据。

        Args:
        - address (int): 内存地址
        - value (int): 待写入的数据

        Returns:
        - None
        """
        self.data[address] = value


class FPUnit:
    def __init__(self, unit_type, num_reservation_stations, execution_cycles, bus=None):
        """
        浮点数执行单元类，包含多个保留站用于执行浮点数运算。

        Args:
        - unit_type (str): 执行单元类型
        - num_reservation_stations (int): 保留站数量
        - execution_cycles (dict): 不同操作的执行周期
        - bus: 与总线通信的总线对象
        """
        self.unit_type = unit_type
        self.execution_cycles = execution_cycles
        self.reservation_stations = [ReservationStation(name=f"{unit_type}{i + 1}") for i in
                                     range(num_reservation_stations)]
        self.bus = bus

    def issue_instruction(self, instruction, vj, vk, qj, qk, rob_index):
        """
        发射指令到浮点数执行单元。

        Args:
        - instruction: 待发射的指令
        - vj: 指令操作数vj
        - vk: 指令操作数vk
        - qj: 指令操作数qj
        - qk: 指令操作数qk
        - rob_index (int): 与ROB相关联的索引

        Returns:
        - bool: 如果成功发射指令，返回True；否则返回False
        """
        for rs in self.reservation_stations:
            if not rs.busy:
                # 如果 Reservation Station 可用，发射指令，即在Reservation Station中加入对应属性
                rs.busy = True
                rs.op = instruction.opcode
                rs.vj = vj
                rs.vk = vk
                rs.qj = qj
                rs.qk = qk
                rs.dest = instruction.destination
                rs.rob_index = rob_index
                rs.remain_time = self.execution_cycles.get(instruction.opcode, 1)
                rs.issue_this_cycle = True
                return True

        # 如果没有可用的 Reservation Station，指令发射失败
        print(f"No available Reservation Station for instruction: {instruction.opcode} {instruction.destination}, "
              f"{vj}, {vk}, {qj}, {qk}, {rob_index}")
        return False

    def update(self):
        """
        在时钟周期中执行的操作，读取总线上的数据并更新浮点数执行单元状态。

        Returns:
        - None
        """
        # 从总线中读取写入的数据
        label, data = self.bus.read()

        for rs in self.reservation_stations:
            if rs.busy:
                if rs.qj or rs.qk:  # 操作数未就绪，判断总线中广播数据是否需要
                    if data and rs.qj == label:
                        rs.vj = f"#{label}"
                        rs.qj = None
                    elif data and rs.qk == label:
                        rs.vk = f"#{label}"
                        rs.qk = None
                elif rs.remain_time > 0:  # 操作数已经就绪，执行
                    if rs.issue_this_cycle:  # 因为发射指令需要一个周期，因此需要跳过新发射的指令
                        rs.issue_this_cycle = False
                        continue
                    self.bus.exec.append(rs.rob_index)  # 将正在执行EX阶段的指令传递给ROB，用以修改ROB状态
                    # 执行阶段
                    rs.remain_time -= 1
                    if rs.remain_time == 0:  # 若执行完成，根据要求输出格式记录结果
                        if isinstance(rs.vj, str):
                            vj_result = rs.vj
                        else:
                            vj_result = f"Reg[F{rs.vj}]"
                        if isinstance(rs.vk, str):
                            vk_result = rs.vk
                        else:
                            vk_result = f"Reg[F{rs.vk}]"
                        if rs.op == "ADDD":
                            result = f"{vj_result} + {vk_result}"
                        elif rs.op == "SUBD":
                            result = f"{vj_result} - {vk_result}"
                        elif rs.op == "MULTD":
                            result = f"{vj_result} * {vk_result}"
                        elif rs.op == "DIVD":
                            result = f"{vj_result} / {vk_result}"
                        else:
                            raise ValueError(f"Error operation!")
                        if not self.bus.write(rs.rob_index, result):  # 若当前总线有写入阶段，则需要下个周期再次尝试写入
                            rs.remain_time += 1
                else:
                    rs.busy = False
                rs.issue_this_cycle = False

    def finish(self):
        """
        检查浮点数执行单元中的所有保留站是否都已完成。

        Returns:
        - bool: 如果所有保留站都已完成，返回True；否则返回False
        """
        for rs in self.reservation_stations:
            if rs.busy:
                return False
        return True
