#! /usr/bin/env python

from __future__ import print_function
import argparse, sys

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument('file', help='Input file', nargs='?')
arg_parser.add_argument('-d', '--debug', help='Debug', action='store_true')
arg_parser.add_argument('--disasm', help='Disassemble', action='store_true')

class BFError(Exception): pass
class BFRuntimeError(BFError): pass
class BFCompileError(BFError): pass
class BFInternalError(BFError): pass

class TermIO:
    def __init__(self):
        self.queue = []
        self._getch = self._getgetch()
    def _getgetch(self):
        if not sys.stdin.isatty():
            return lambda: sys.stdin.read(1)
        try:
            import msvcrt
            return msvcrt.getch
        except ImportError:
            import tty, termios
            def getch():
                infile = sys.stdin.fileno()
                old_settings = termios.tcgetattr(infile)
                try:
                    tty.setraw(infile)
                    return sys.stdin.read(1)
                finally:
                    termios.tcsetattr(infile, termios.TCSADRAIN, old_settings)
            return getch
    def getch(self):
        ch = self._getch()
        if ch == '\x03':
            raise KeyboardInterrupt
        if ch == '\x04':
            raise EOFError
        if ch == '\r':
            return '\n'
        return ch

getch = TermIO().getch

class BFVM:
    def __init__(self, mem_size=1024, cell_size=256):
        self.mem_size = int(mem_size)
        self.mem_max = self.mem_size - 1
        self.cell_size = int(cell_size)
        self.cell_max = self.cell_size - 1
        self.reset()

    def reset(self):
        self.mem_ptr = 0
        self.memory = [0] * self.mem_size
        self.code_ptr = 0

    def run(self, instructions):
        try:
            self.code = instructions
            while self.code_ptr < len(self.code):
                self.code[self.code_ptr](self)
                self.code_ptr += 1
        except Exception as e:
            raise BFInternalError('%s: %s' % (type(e).__name__, e))

class BFCompiler:
    def __init__(self, instruction_set):
        self.instruction_set = instruction_set
    def compile(self, code):
        instructions = []
        orig_code = code
        ch = ''
        try:
            while len(code):
                ch = code[0]
                if ch in self.instruction_set.instructions:
                    inst, code = self.instruction_set.instructions[ch](code, instructions)
                    if inst is None:
                        continue
                    inst.type = self.instruction_set.instructions[ch]
                    if not hasattr(inst, 'repr'):
                        inst.repr = '<unknown>'
                    if not hasattr(inst, 'src'):
                        inst.src = '???'
                    instructions.append(inst)
                else:
                    code = code[1:]
        except BFCompileError as e:
            raise BFCompileError('Compile-time error at char %i (%s): %s' %
                                 (len(orig_code) - len(code), ch, e))
        return instructions

    def disasm(self, instructions, start=0, end=None, code_ptr=-1):
        if end is None or end >= len(instructions):
            end = len(instructions) - 1
        result = ''
        for i in range(start, end + 1):
            result += '%s %5i: %-15s | %s\n' % \
                ('*' if i == code_ptr else ' ', i, instructions[i].repr, instructions[i].src)
        return result

class BFDefaultInstructions:
    def __init__(self, **kwargs):
        self.opts = kwargs
        self.instructions = {
            '+': self.add,
            '-': self.add,
            '>': self.move_ptr,
            '<': self.move_ptr,
            '[': self.open_loop,
            ']': self.close_loop,
            ',': self.getch,
            '.': self.putch,
        }
    def add(self, src, compiled):
        delta = 0
        orig_src = ''
        while src[0] in ('+', '-'):
            delta += (src[0] == '+') - (src[0] == '-')
            orig_src += src[0]
            src = src[1:]
            if not len(src):
                break
        if delta == 0:
            return None, src
        def f(vm):
            vm.memory[vm.mem_ptr] = (vm.memory[vm.mem_ptr] + delta) % vm.cell_size
        f.repr = 'add %i' % delta
        f.src = orig_src
        return f, src
    def move_ptr(self, src, compiled):
        delta = 0
        orig_src = ''
        while src[0] in ('<', '>'):
            delta += (src[0] == '>') - (src[0] == '<')
            orig_src += src[0]
            src = src[1:]
            if not len(src):
                break
        if delta == 0:
            return None, src
        def f(vm):
            vm.mem_ptr = (vm.mem_ptr + delta) % vm.mem_size
        f.repr = 'move %i' % delta
        f.src = orig_src
        return f, src
    def open_loop(self, src, compiled):
        def f(vm):
            if not vm.memory[vm.mem_ptr]:
                if f.close_addr is None:
                    raise BFRuntimeError('Unclosed loop')
                vm.code_ptr = f.close_addr
        f.repr = 'loop'
        f.src = src[0]
        f.close_addr = None
        return f, src[1:]
    def close_loop(self, src, compiled):
        open_addr = len(compiled) - 1
        depth = 1
        inst = None
        while open_addr >= 0 and depth > 0:
            inst = compiled[open_addr]
            if inst.type == self.open_loop:
                depth -= 1
            if inst.type == self.close_loop:
                depth += 1
            open_addr -= 1
        if depth > 0:
            raise BFCompileError('Unopened loop')
        inst.close_addr = len(compiled)  # Address of this instruction
        def f(vm):
            if vm.memory[vm.mem_ptr]:
                vm.code_ptr = open_addr
        f.repr = 'end loop'
        f.src = src[0]
        return f, src[1:]
    def getch(self, src, compiled):
        def f(vm):
            vm.memory[vm.mem_ptr] = ord(getch())
        f.repr = 'getch'
        f.src = src[0]
        return f, src[1:]
    def putch(self, src, compiled):
        def f(vm):
            sys.stdout.write(chr(vm.memory[vm.mem_ptr]))
            sys.stdout.flush()
        f.repr = 'putch'
        f.src = src[0]
        return f, src[1:]

def load_file(filename):
    with open(filename) as f:
        return f.read()

def main(args):
    code = None
    if args.file is not None:
        code = load_file(args.file)
    if code is not None:
        vm = BFVM()
        compiler = BFCompiler(BFDefaultInstructions())
        bytecode = compiler.compile(code)
        if args.disasm:
            print(compiler.disasm(bytecode))
            return
        try:
            vm.run(bytecode)
        except KeyboardInterrupt:
            if not args.debug:
                raise
        if args.debug:
            print('\nLast state:')
            print('IP=%i\tMP=%i' % (vm.code_ptr, vm.mem_ptr))
            print('Disassembly: ')
            print(compiler.disasm(bytecode, max(0, vm.code_ptr - 10), vm.code_ptr + 10, code_ptr=vm.code_ptr))
            mem = vm.memory[:]
            mem[vm.mem_ptr] = '[%i]' % mem[vm.mem_ptr]
            mem = mem[max(0, vm.mem_ptr - 20):vm.mem_ptr + 20]
            print('Memory: ' + ' '.join([str(i) for i in mem]))


if __name__ == '__main__':
    main(arg_parser.parse_args())
