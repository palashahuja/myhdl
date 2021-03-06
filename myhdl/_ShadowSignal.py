#  This file is part of the myhdl library, a Python package for using
#  Python as a Hardware Description Language.
#
#  Copyright (C) 2003-2011 Jan Decaluwe
#
#  The myhdl library is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public License as
#  published by the Free Software Foundation; either version 2.1 of the
#  License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful, but
#  WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.

#  You should have received a copy of the GNU Lesser General Public
#  License along with this library; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

""" Module that provides the ShadowSignal classes


"""

import warnings
from copy import deepcopy

from myhdl._Signal import _Signal
from myhdl._Waiter import _SignalWaiter, _SignalTupleWaiter
from myhdl._intbv import intbv
from myhdl._simulator import _siglist

# shadow signals
        
        
class _ShadowSignal(_Signal):

    __slots__ = ('_waiter', )

    def __init__(self, val):
        _Signal.__init__(self, val)
        # self._driven = True # set this in conversion analyzer

    # remove next attribute assignment
    next = property(_Signal._get_next, None, None, "'next' access methods")


        
class _SliceSignal(_ShadowSignal):

    __slots__ = ('_sig', '_left', '_right')

    def __init__(self, sig, left, right=None):
        ### XXX error checks
        if right is None:
            _ShadowSignal.__init__(self, sig[left])
        else:
            _ShadowSignal.__init__(self, sig[left:right])
        self._sig = sig
        self._left = left
        self._right = right
        if right is None:
            gen = self._genfuncIndex()
        else:
            gen = self._genfuncSlice()
        self._waiter = _SignalWaiter(gen)

    def _genfuncIndex(self):
        sig, index = self._sig, self._left
        set_next = _ShadowSignal._set_next
        while 1:
            set_next(self, sig[index])
            yield sig

    def _genfuncSlice(self):
        sig, left, right = self._sig, self._left, self._right
        set_next = _Signal._set_next
        while 1:
            set_next(self, sig[left:right])
            yield sig

    def _setName(self, hdl):
        if self._right is None:       
            if hdl == 'Verilog':
                self._name = "%s[%s]" % (self._sig._name, self._left)
            else:
                self._name = "%s(%s)" % (self._sig._name, self._left)
        else:
            if hdl == 'Verilog':
                self._name = "%s[%s-1:%s]" % (self._sig._name, self._left, self._right)
            else:
                self._name = "%s(%s-1 downto %s)" % (self._sig._name, self._left, self._right)

    def _markRead(self):
        self._read = True
        self._sig._read = True

    def _markUsed(self):
        self._used = True
        self._sig._used = True
        

    def toVerilog(self):
        if self._right is None:
            return "assign %s = %s[%s];" % (self._name, self._sig._name, self._left)
        else:
            return "assign %s = %s[%s-1:%s];" % (self._name, self._sig._name, self._left, self._right)
    
    def toVHDL(self):
        if self._right is None:
            return "%s <= %s(%s);" % (self._name, self._sig._name, self._left)
        else:
            return "%s <= %s(%s-1 downto %s);" % (self._name, self._sig._name, self._left, self._right)



class ConcatSignal(_ShadowSignal):

    __slots__ = ('_args',)

    def __init__(self, *args):
        assert len(args) >= 2
        self._args = args
        ### XXX error checks
        nrbits = 0
        for a in args:
            nrbits += len(a)
        ini = intbv(0)[nrbits:]
        hi = nrbits
        for a in args:
            lo = hi - len(a)
            ini[hi:lo] = a
            hi = lo
        _ShadowSignal.__init__(self, ini)
        gen = self.genfunc()
        self._waiter = _SignalTupleWaiter(gen)

    def genfunc(self):
        set_next = _ShadowSignal._set_next
        args = self._args
        nrbits = self._nrbits
        newval = intbv(0)[nrbits:]
        while 1:
            hi = nrbits
            for a in args:
                lo = hi - len(a)
                newval[hi:lo] = a
                hi = lo
            set_next(self, newval)
            yield args

    def _markRead(self):
        self._read = True
        for s in self._args:
            s._markRead() 

    def _markUsed(self):
        self._used = True
        for s in self._args:
            s._markUsed() 

    def toVHDL(self):
        lines = []
        hi = self._nrbits
        for a in self._args:
            lo = hi - len(a)
            if len(a) == 1:
                lines.append("%s(%s) <= %s;" % (self._name, lo, a._name))
            else:
                lines.append("%s(%s-1 downto %s) <= %s;" % (self._name, hi, lo, a._name))
            hi = lo
        return "\n".join(lines)

    def toVerilog(self):
        lines = []
        hi = self._nrbits
        for a in self._args:
            lo = hi - len(a)
            if len(a) == 1:
                lines.append("assign %s[%s] = %s;" % (self._name, lo, a._name))
            else:
                lines.append("assign %s[%s-1:%s] = %s;" % (self._name, hi, lo, a._name))
            hi = lo
        return "\n".join(lines)


# Tristate signal


class BusContentionWarning(UserWarning):
    pass

warnings.filterwarnings('always', r".*", BusContentionWarning)

# def Tristate(val, delay=None):
#     """ Return a new Tristate(default or delay 0) or DelayedTristate """
#     if delay is not None:
#         if delay < 0:
#             raise TypeError("Signal: delay should be >= 0")
#         return _DelayedTristate(val, delay)
#     else:
#         return _Tristate(val)
 
 
def TristateSignal(val):
    return _TristateSignal(val)


class _TristateSignal(_ShadowSignal):

    __slots__ = ('_drivers', '_orival' )
            
    def __init__(self, val):
        self._drivers = []
        # construct normally to set type / size info right
        _ShadowSignal.__init__(self, val)     
        self._orival = deepcopy(val) # keep for drivers
        # reset signal values to None
        self._next = self._val = self._init = None
        self._waiter = _SignalTupleWaiter(self._resolve())

    def driver(self):
        d = _TristateDriver(self)
        self._drivers.append(d)
        return d

    def _resolve(self):
        # set_next = _ShadowSignal._set_next
        senslist = self._drivers
        while 1:
            yield senslist
            res = None
            for d in senslist:
                if res is None:
                    res = d._val
                elif d._val is not None:
                    warnings.warn("Bus contention", category=BusContentionWarning)
                    res = None
                    break
            self._next = res
            _siglist.append(self)


    def toVerilog(self):
        lines = []
        for d in self._drivers:
            lines.append("assign %s = %s;" % (self._name, d._name))
        return "\n".join(lines)

    def toVHDL(self):
        lines = []
        for d in self._drivers:
            lines.append("%s <= %s;" % (self._name, d._name))
        return "\n".join(lines)



class _TristateDriver(_Signal):

    __slots__ = ('_sig',)
    
    def __init__(self, sig):
        _Signal.__init__(self, sig._orival)
        # reset signal values to None
        self._next = self._val = self._init = None
        self._sig = sig

    def _set_next(self, val):
        if isinstance(val, _Signal):
            val = val._val
        if val is None:
            self._next = None
        else:     
            # restore original value to cater for intbv handler
            self._next = self._sig._orival
            self._setNextVal(val)
        _siglist.append(self)   
         
    # redefine property because standard inheritance doesn't work for setter/getter functions
    next = property(_Signal._get_next, _set_next, None, "'next' access methods")
