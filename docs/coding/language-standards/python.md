# Python 代码评审规范

> 文档版本：v1.0 | 适用语言：Python（.py, .pyw）

---

## 1. 资源管理 <critical>

所有外部资源（文件、网络连接、数据库连接、锁）使用后必须显式关闭或释放。

### 1.1 文件操作
- **必须**使用 `with` 语句管理文件句柄：`with open(...) as f:`
- 禁止裸 `f.open()` 后不调用 `f.close()`
- 使用 `tempfile` 模块处理临时文件，而非手动创建

### 1.2 数据库连接
- 使用上下文管理器管理连接生命周期
- ORM session 使用后必须关闭或释放
- 连接池用完必须归还

### 1.3 线程/进程池
- `ThreadPoolExecutor` / `ProcessPoolExecutor` 使用后必须 `shutdown()`
- 推荐使用 `with` 语句：`with ThreadPoolExecutor() as executor:`

### 1.4 网络连接
- HTTP 会话（`requests.Session`、`aiohttp.ClientSession`）使用后必须关闭
- WebSocket 连接必须正确关闭

---

## 2. 并发安全 <critical>

### 2.1 共享状态保护
- 多线程访问共享变量必须使用 `threading.Lock` 或 `threading.RLock`
- 异步代码中共享状态必须使用 `asyncio.Lock`
- 避免使用 `threading.Thread` 裸创建线程，推荐 `ThreadPoolExecutor`

### 2.2 异步代码
- 异步函数中避免阻塞调用（`time.sleep()` → `asyncio.sleep()`）
- 避免在异步代码中调用同步 IO 函数
- 在异步上下文中使用 `asyncio.run()` 仅限入口点

### 2.3 全局状态
- 避免可变全局变量在多线程中共享
- 类变量（class attribute）不是线程安全的

---

## 3. 正确性 <warning>

### 3.1 类型标注
- 函数返回 `None` 必须标注 `Optional[...]` 或 `... | None`
- 类型标注与实际返回值必须一致
- 使用 `TypedDict` / `dataclass` 而非裸字典传递结构化数据

### 3.2 异常处理
- `except:` 必须指定异常类型（禁止裸 `except:`）
- 避免空的 `except: pass`，除非明确注释说明原因
- `try` 块范围应尽量小，只包裹可能抛出异常的代码

### 3.3 常见陷阱
- 禁止可变默认参数：`def foo(x=[])` → `def foo(x=None)`
- 浅拷贝/深拷贝区分明确：使用 `copy.copy()` vs `copy.deepcopy()`
- 循环内修改正在遍历的列表应使用副本：`for item in list[:]:`
- 字符编码必须显式指定，禁止依赖系统默认编码

### 3.4 逻辑错误
- 条件判断边界值正确（使用 `<=` 而非 `<` 等）
- 确保异常分支有返回值或显式 `raise`
- 避免无意义的 `if True:` / `if False:` 判断

---

## 4. 安全 <warning>

### 4.1 危险函数
- **禁止** `eval()`、`exec()`、`compile()` 处理不可信输入
- **禁止** `subprocess` 的 `shell=True` 参数，使用列表参数替代
- **禁止** `pickle.loads()` 处理不可信数据
- 避免 `os.system()`，使用 `subprocess.run()` 替代

### 4.2 注入防护
- SQL 查询**必须**使用参数化查询或 ORM，禁止字符串拼接
- 模板渲染需防范模板注入（Jinja2 autoescape 开启）
- 使用 `shlex.quote()` 处理 shell 参数

### 4.3 敏感信息
- 禁止硬编码密钥、密码、Token 在代码中
- 日志中禁止输出敏感信息（脱敏处理）
- 使用环境变量或 secrets 管理工具加载敏感配置

---

## 5. 性能 <info>

### 5.1 查询优化
- 避免循环内查询数据库（N+1 问题），使用 `select_related` / `prefetch_related` 预加载
- 批量操作使用 `bulk_create` / `bulk_update`
- 高频读取的数据考虑缓存

### 5.2 代码执行效率
- 列表推导优于 `for` + `append` 模式
- 生成器表达式优于列表推导（内存不敏感时除外）
- 频繁调用的函数考虑使用 `lru_cache` / `functools.cache`

### 5.3 资源开销
- 大文件逐行读取而非一次性加载到内存
- 避免在热点路径中创建不必要的临时对象
- 使用 `__slots__` 减少大量实例的内存开销（性能敏感场景）

---

## 6. 代码规范 <info>

### 6.1 命名规范 (PEP 8)
- 变量/函数/方法：`snake_case`
- 类名：`PascalCase`
- 常量：`UPPER_CASE`
- 私有成员：前置单下划线 `_private`
- 避免使用双下划线 `__name_mangling` 除非真的需要

### 6.2 函数设计
- 单个函数不超过 **50 行**（硬上限 100 行）
- 圈复杂度（McCabe）不超过 **10**
- 参数不超过 **5 个**（超过考虑使用 dataclass 或拆解）
- 嵌套层级不超过 **4 层**（超过考虑提取子函数或 early return）

### 6.3 模块设计
- 每个模块遵循单一职责原则
- 循环依赖判定为设计缺陷
- 公共函数和类必须有 docstring（Google 风格）
- 类型注解覆盖所有公共接口

### 6.4 注释
- 注释说明"为什么"而非"是什么"
- 复杂算法必须附注释说明思路
- `TODO` / `FIXME` / `HACK` 标记必须有关联 Issue 编号
