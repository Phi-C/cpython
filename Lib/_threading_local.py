"""Thread-local objects.

(Note that this module provides a Python version of the threading.local
 class.  Depending on the version of Python you're using, there may be a
 faster one available.  You should always import the `local` class from
 `threading`.)
"""

from weakref import ref
from contextlib import contextmanager

__all__ = ["local"]

# We need to use objects from the threading module, but the threading
# module may also want to use our `local` class, if support for locals
# isn't compiled in to the `thread` module.  This creates potential problems
# with circular imports.  For that reason, we don't import `threading`
# until the bottom of this file (a hack sufficient to worm around the
# potential problems).  Note that all platforms on CPython do have support
# for locals in the `thread` module, and there is no circular import problem
# then, so problems introduced by fiddling the order of imports here won't
# manifest.

class _localimpl:
    """A class managing thread-local dicts"""
    __slots__ = 'key', 'dicts', 'localargs', 'locallock', '__weakref__'

    def __init__(self):
        # The key used in the Thread objects' attribute dicts.
        # We keep it a string for speed but make it unlikely to clash with
        # a "real" attribute.
        self.key = '_threading_local._localimpl.' + str(id(self))
        # 这里的self.dicts是实现threading.local里最重要的数据结构, 里面存储了每个线程的thead-local attributes
        # { id(Thread) -> (ref(Thread), thread-local dict) }
        self.dicts = {}

    def get_dict(self):
        """Return the dict for the current thread. Raises KeyError if none
        defined."""
        thread = current_thread()
        return self.dicts[id(thread)][1]

    def create_dict(self):
        """Create a new dict for the current thread, and return it."""
        localdict = {}
        key = self.key
        thread = current_thread()
        idt = id(thread)
        def local_deleted(_, key=key):
            # When the localimpl is deleted, remove the thread attribute.
            thread = wrthread()
            if thread is not None:
                del thread.__dict__[key]
        def thread_deleted(_, idt=idt):
            # When the thread is deleted, remove the local dict.
            # Note that this is suboptimal if the thread object gets
            # caught in a reference loop. We would like to be called
            # as soon as the OS-level thread ends instead.
            local = wrlocal()
            if local is not None:
                dct = local.dicts.pop(idt)
        # weakref.ref允许你引用一个对象, 但不会阻止它被垃圾回收. 当对象被回收时, 弱引用会自动失效
        # weakref.ref(a, b): a是可弱引用的对象.e.g.类实例、list、dict等, 不能是int, str, tuple等不可变类型
        # b是当a被垃圾回收时的回调函数
        wrlocal = ref(self, local_deleted)
        wrthread = ref(thread, thread_deleted)
        thread.__dict__[key] = wrlocal
        self.dicts[idt] = wrthread, localdict
        return localdict


# 通过_patch临时替换__dict__实现线程隔离
@contextmanager
def _patch(self):
    impl = object.__getattribute__(self, '_local__impl')
    try:
        # 这里get_dict(): key=id(current_thread()); value=local_dict{}
        dct = impl.get_dict()
    except KeyError:
        dct = impl.create_dict()
        args, kw = impl.localargs
        self.__init__(*args, **kw)
    with impl.locallock:
        object.__setattr__(self, '__dict__', dct)
        yield


class local:
    # 如果定义了__slots__, 对象的属性将不再存储在__dict__中, 而是直接通过固定大小的数组(或类似结构)存储, 从而节省内存
    # 如果注释掉这行, 会报错: AttributeError: 'local' object has no attribute '_local__impl'
    # 因为_patch会将原本的__dict__覆盖掉
    __slots__ = '_local__impl', '__dict__'

    def __new__(cls, /, *args, **kw):
        # 用户传了参数(args或者kwargs), 但是没有重写__init__(即仍然使用默认的object.__init__)
        # 这么做是为了让每个线程独立初始化
        if (args or kw) and (cls.__init__ is object.__init__):
            raise TypeError("Initialization arguments are not supported")
        self = object.__new__(cls)
        impl = _localimpl()
        impl.localargs = (args, kw)
        impl.locallock = RLock()
        object.__setattr__(self, '_local__impl', impl)
        # We need to create the thread dict in anticipation of
        # __init__ being called, to make sure we don't call it
        # again ourselves.
        impl.create_dict()
        return self

    def __getattribute__(self, name):
        with _patch(self):
            return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        if name == '__dict__':
            raise AttributeError(
                "%r object attribute '__dict__' is read-only"
                % self.__class__.__name__)
        with _patch(self):
            return object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if name == '__dict__':
            raise AttributeError(
                "%r object attribute '__dict__' is read-only"
                % self.__class__.__name__)
        with _patch(self):
            return object.__delattr__(self, name)


from threading import current_thread, RLock
