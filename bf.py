#! /usr/bin/env python

from __future__ import print_function
import argparse, sys

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument('file', help='Input file', nargs='?')

class BFError(Exception): pass
class BFRuntimeError(Exception): pass
class BFCompileError(Exception): pass

class TermIO:
    def __init__(self):
        self.queue = []
        self.getch = self._getgetch()
    def _getgetch(self):
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
        self.code = instructions
        while self.code_ptr < len(self.code):
            self.code[self.code_ptr](self)
            self.code_ptr += 1

class BFCompiler:
    def __init__(self, instruction_set):
        self.instruction_set = instruction_set
    def compile(self, code):
        instructions = []
        while len(code):
            ch = code[0]
            if ch in self.instruction_set.instructions:
                inst, code = self.instruction_set.instructions[ch](code, instructions)
                inst.type = self.instruction_set.instructions[ch]
                instructions.append(inst)
            else:
                code = code[1:]
        return instructions

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
        while src[0] in ('+', '-'):
            delta += (src[0] == '+') - (src[0] == '-')
            src = src[1:]
        def f(vm):
            vm.memory[vm.mem_ptr] += delta
            vm.memory[vm.mem_ptr] %= vm.mem_size
        return f, src
    def move_ptr(self, src, compiled):
        delta = 0
        while src[0] in ('<', '>'):
            delta += (src[0] == '>') - (src[0] == '<')
            src = src[1:]
        def f(vm):
            vm.mem_ptr += delta
            vm.mem_ptr %= vm.mem_size
        return f, src
    def open_loop(self, src, compiled):
        def f(vm):
            if not vm.memory[vm.mem_ptr]:
                if f.close_addr is None:
                    raise BFRuntimeError('Unclosed loop')
                vm.code_ptr = f.close_addr
        f.close_addr = None
        return f, src[1:]
    def close_loop(self, src, compiled):
        open_addr = len(compiled) - 1
        depth = 1
        inst = None
        while open_addr > 0 and depth > 0:
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
        return f, src[1:]
    def getch(self, src, compiled):
        def f(vm):
            vm.memory[vm.mem_ptr] = ord(getch())
        return f, src[1:]
    def putch(self, src, compiled):
        def f(vm):
            sys.stdout.write(chr(vm.memory[vm.mem_ptr]))
            sys.stdout.flush()
        return f, src[1:]

def load_file(filename):
    with open(filename) as f:
        return f.read()

def run_code(code):
    vm = BFVM()
    vm.run(BFCompiler(BFDefaultInstructions()).compile(code))

def main(args):
    if args.file is not None:
        run_code(load_file(args.file))

if __name__ == '__main__':
    main(arg_parser.parse_args())
