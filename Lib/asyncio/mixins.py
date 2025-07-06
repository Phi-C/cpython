"""Event loop mixins."""

import threading
from . import events

_global_lock = threading.Lock()


# mixin的思想很简单: 希望能够为类和对象提供扩展新的功能，但不用继承
# 上面的继承不是指形式上的继承, 而是继承的语义is-a关系
# Mixin不是is-a关系, 而是-able关系
class _LoopBoundMixin:
    _loop = None

    def _get_loop(self):
        loop = events._get_running_loop()

        # Double-Checked Locking: 双重检查锁
        if self._loop is None:
            with _global_lock:
                # 这里需要再判断一次, 以防有其他线程已经将loop赋给了self._loop
                if self._loop is None:
                    self._loop = loop
        if loop is not self._loop:
            raise RuntimeError(f'{self!r} is bound to a different event loop')
        return loop
