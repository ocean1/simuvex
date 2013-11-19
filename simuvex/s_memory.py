#!/usr/bin/env python

import logging
import itertools
import cooldict

l = logging.getLogger("s_memory")

import symexec
import s_exception

addr_mem_counter = itertools.count()
var_mem_counter = itertools.count()
# Conventions used:
# 1) The whole memory is readable
# 2) Memory locations are by default writable
# 3) Memory locations are by default not executable

class SimMemoryError(s_exception.SimError):
	pass

class Vectorizer(cooldict.CachedDict):
	def __init__(self, backer):
		super(Vectorizer, self).__init__(backer)

	def default_cacher(self, k):
		b = self.backer[k]
		if type(b) in ( int, str ):
			b = symexec.BitVecVal(ord(self.backer[k]), 8)

		self.cache[k] = b
		return b


class SimMemory:
	def __init__(self, backer, bits=None, id="mem"):
		if not isinstance(backer, cooldict.BranchingDict):
			backer = cooldict.BranchingDict(backer)

		self.mem = backer
		self.limit = 1024
		self.bits = bits if bits else 64
		self.max_mem = 2**self.bits
		self.id = id

	def __read_from(self, addr, num_bytes):
		bytes = [ ]
		for i in range(0, num_bytes):
			try:
				bytes.append(self.mem[addr+i])
			except KeyError:
				b = symexec.BitVec("%s_%d" % (self.id, var_mem_counter.next()), 8)
				self.mem[addr+i] = b
				bytes.append(b)

		if len(bytes) == 1:
			return bytes[0]
		else:
			return symexec.Concat(*bytes)

	def __write_to(self, addr, cnt):
		for off in range(0, cnt.size(), 8):
			target = addr + off/8
			new_content = symexec.Extract(cnt.size() - off - 1, cnt.size() - off - 8, cnt)
			self.mem[target] = new_content

	def concretize_addr(self, v, strategies):
		if v.is_symbolic and not v.satisfiable():
			raise SimMemoryError("Trying to concretize with unsat constraints.")

		# if there's only one option, let's do it
		if v.is_unique():
			return [ v.any() ]

		for s in strategies:
			if s == "free":
				# TODO
				pass
			if s == "writeable":
				# TODO
				pass
			if s == "executable":
				# TODO
				pass
			if s == "symbolic":
				# if the address concretizes to less than the threshold of values, try to keep it symbolic
				if v.max() - v.min() < self.limit:
					return v.any_n(self.limit)
			if s == "any":
				return [ v.any() ]

		raise SimMemoryError("Unable to concretize address with the provided strategies.")

	def concretize_write_addr(self, dst):
		return self.concretize_addr(dst, strategies = [ "free", "writeable", "any" ])

	def concretize_read_addr(self, dst):
		return self.concretize_addr(dst, strategies=['symbolic', 'any'])

	def store(self, dst, cnt):
		addr = self.concretize_write_addr(dst)[0]
		self.__write_to(addr, cnt)
		return [dst.expr == addr]

	def load(self, dst, size):
		size_b = size/8
		addrs = self.concretize_read_addr(dst)

		# if there's a single address, it's easy
		if len(addrs) == 1:
			return self.__read_from(addrs[0], size/8), [ dst.expr == addrs[0] ]

		# otherwise, create a new symbolic variable and return the mess of constraints and values
		m = symexec.BitVec("%s_addr_%s" %(self.id, addr_mem_counter.next()), self.bits)
		e = symexec.Or(*[ symexec.And(m == self.__read_from(addr, size_b), dst.expr == addr) for addr in addrs ])
		return m, [ e ]

	def copy(self):
		l.debug("Copying %d bytes of memory with id %s." % (len(self.mem), self.id))
		c = SimMemory(self.mem.branch(), bits=self.bits, id=self.id)
		return c