# Micro-GenBI UI 设计规范

> 基于 Tesla Design System 灵感的企业级 Text2SQL 数据分析平台 UI 设计规范

## 1. 设计理念

### 1.1 设计哲学

Micro-GenBI 作为一个专业的数据分析工具，采用 **Tesla 极简主义** 设计风格：
- **极简克制**：界面干净利落，让数据和内容成为主角
- **功能优先**：每个元素都有明确的用途，无多余装饰
- **技术感**：精准的线条、微妙的圆角、冷静的色调

### 1.2 视觉主题

```
┌─────────────────────────────────────────────────────────────────┐
│                     Micro-GenBI 视觉体系                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   主色调：Electric Blue (#3E6AE1)                                │
│   用途：主要按钮、进度指示、关键信息强调                              │
│                                                                  │
│   背景色：Pure White (#FFFFFF)                                    │
│   用途：主背景、卡片、对话框                                       │
│                                                                  │
│   文字层级：                                                      │
│   - Carbon (#171A20) → 标题、重要文字                              │
│   - Graphite (#393C41) → 正文、说明文字                            │
│   - Pewter (#5C5E62) → 次要文字、标签                              │
│   - Silver (#8E8E8E) → 占位符、禁用状态                            │
│                                                                  │
│   辅助色：Light Ash (#F4F4F4)                                    │
│   用途：输入框背景、悬停状态、分区背景                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 颜色系统

### 2.1 品牌色

| 颜色名称 | 色值 | 用途 |
|---------|------|------|
| Electric Blue | `#3E6AE1` | 主要 CTA 按钮、进度指示器、链接 |
| Blue Hover | `#2F55B8` | 按钮悬停状态 |

### 2.2 表面色

| 颜色名称 | 色值 | 用途 |
|---------|------|------|
| Pure White | `#FFFFFF` | 主背景、卡片、输入框 |
| Light Ash | `#F4F4F4` | 消息气泡背景、表格斑马纹 |
| Carbon | `#171A20` | 深色表面、用户头像背景 |
| Graphite | `#393C41` | 正文、默认文字色 |

### 2.3 中性色

| 颜色名称 | 色值 | 用途 |
|---------|------|------|
| Pewter | `#5C5E62` | 次要文字、图标 |
| Silver | `#8E8E8E` | 占位符、禁用文字 |
| Cloud | `#EEEEEE` | 分割线、边框 |
| Pale Silver | `#D0D1D2` | 输入框边框 |

### 2.4 语义色

| 状态 | 颜色 | 用途 |
|------|------|------|
| 成功 | `#10B981` | 执行成功、完成状态 |
| 警告 | `#F59E0B` | 警告提示 |
| 错误 | `#EF4444` | 错误消息、失败状态 |
| 信息 | `#3E6AE1` | 信息提示（复用主色） |

---

## 3. 字体系统

### 3.1 字体选择

```css
/* 字体栈 */
font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei',
             -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
```

### 3.2 字体层级

| 用途 | 字号 | 字重 | 行高 | 字间距 |
|------|------|------|------|--------|
| Logo 标题 | 14px | 500 | 1.2 | -0.3px |
| Logo 副标题 | 11px | 400 | 1.2 | -0.2px |
| 页面标题 | 26px | 500 | 1.2 | -0.5px |
| 区块标题 | 13px | 500 | 1.3 | -0.2px |
| 正文 | 14px | 400 | 1.6 | -0.2px |
| 辅助文字 | 13px | 400 | 1.5 | -0.2px |
| 标签文字 | 11px | 400 | 1.4 | -0.2px |
| 代码/数据 | 13px | 400 | 1.6 | 0 |

---

## 4. 间距系统

### 4.1 基础间距单位

```
间距基准：8px

xs  = 4px   （紧凑间距）
sm  = 8px   （小间距）
md  = 12px  （中等间距）
lg  = 16px  （标准间距）
xl  = 24px  （大间距）
xxl = 32px  （区块间距）
```

### 4.2 组件间距

| 组件 | 内边距 | 外边距 |
|------|--------|--------|
| 按钮 | 0 16px, height: 36-40px | gap: 8px |
| 卡片 | 14px 16px | margin-bottom: 12px |
| 输入框 | 9px 12px | margin-bottom: 10px |
| 消息气泡 | 12px 16px | margin-bottom: 12-16px |
| 侧边栏项目 | 7px 8px | margin-bottom: 1px |

---

## 5. 圆角系统

| 用途 | 圆角值 | 元素 |
|------|--------|------|
| 微圆角 | 4px | 按钮、输入框、标签 |
| 标准圆角 | 12px | 卡片、模态框、图表容器 |
| 圆形 | 50% | 头像、加载点、图标背景 |

---

## 6. 过渡动画

### 6.1 动画时长

```css
--t: 0.33s;  /* 所有交互的标准过渡时间 */
```

### 6.2 动画类型

| 效果 | 属性 | 时长 | 缓动 |
|------|------|------|------|
| 悬停 | background, color, border-color | 0.33s | ease |
| 焦点 | border-color, box-shadow | 0.33s | ease |
| 出现 | opacity, transform | 0.2s | ease |
| 模态 | opacity | 0.33s | ease |

### 6.3 消息动画

```css
@keyframes msgIn {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
}
/* 持续时间: 0.2s */
```

---

## 7. 核心组件

### 7.1 按钮

#### 主要按钮（Primary CTA）
```css
background: #3E6AE1;      /* Electric Blue */
color: #FFFFFF;
height: 36px;
padding: 0 16px;
border-radius: 4px;
font-size: 13px;
font-weight: 500;
border: none;
transition: background 0.33s;
```
- 用途：发送消息、执行操作

#### 次要按钮（Secondary）
```css
background: #FFFFFF;
color: #393C41;
border: 1px solid #D0D1D2;
height: 32px;
padding: 0 14px;
border-radius: 4px;
font-size: 13px;
font-weight: 500;
transition: background 0.33s, border-color 0.33s;
```
- 用途：取消、复制、辅助操作

#### 图标按钮
```css
width: 32px; height: 32px;
border-radius: 4px;
background: #3E6AE1;  /* 或 #FFFFFF + border */
color: #FFFFFF;      /* 或 #393C41 */
```

### 7.2 输入框

```css
input, textarea {
    background: #FFFFFF;
    border: 1px solid #D0D1D2;
    border-radius: 4px;
    padding: 9px 12px;
    font-size: 14px;
    color: #171A20;
    transition: border-color 0.33s, box-shadow 0.33s;
}

input:focus, textarea:focus {
    border-color: #3E6AE1;
    box-shadow: 0 0 0 2px rgba(62, 106, 225, 0.15);
    outline: none;
}

input::placeholder, textarea::placeholder {
    color: #8E8E8E;
}
```

### 7.3 消息气泡

#### 用户消息
```css
.user-message {
    background: #F4F4F4;
    border-radius: 4px;
    padding: 12px 16px;
    font-size: 14px;
    color: #171A20;
}
```

#### AI 助手消息
```css
.assistant-message {
    padding-left: 42px;  /* 对齐头像 */
}
```

#### 头像
```css
.avatar {
    width: 32px; height: 32px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 500;
    color: #FFFFFF;
}

.user-avatar { background: #3E6AE1; }
.assistant-avatar { background: #171A20; }
```

### 7.4 步骤指示器

```css
.steps-indicator {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 8px 12px;
    background: #F4F4F4;
    border-radius: 4px;
}

.step {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 3px 6px;
    border-radius: 3px;
    font-size: 12px;
    transition: background 0.33s, color 0.33s;
}

.step-icon {
    width: 16px; height: 16px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 9px;
}

.step.active .step-icon { background: #171A20; color: #FFF; }
.step.completed .step-icon { background: #3E6AE1; color: #FFF; }
```

### 7.5 SQL 代码块

```css
.sql-block {
    border-radius: 12px;
    overflow: hidden;
    background: #F4F4F4;
    margin: 10px 0;
}

.sql-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px;
    border-bottom: 1px solid #EEEEEE;
    background: #F4F4F4;
}

.sql-title {
    font-size: 12px;
    font-weight: 500;
    color: #171A20;
}

.sql-badge {
    font-size: 10px;
    font-weight: 500;
    padding: 2px 7px;
    background: #3E6AE1;
    color: #FFF;
    border-radius: 3px;
}

.sql-code {
    padding: 14px 16px;
    font-family: ui-monospace, 'SF Mono', Menlo, monospace;
    font-size: 13px;
    line-height: 1.6;
    background: #FFFFFF;
}

/* SQL 语法高亮 */
.sql-keyword { color: #171A20; font-weight: 500; }
.sql-string { color: #3E6AE1; }
.sql-number { color: #3E6AE1; }
.sql-comment { color: #8E8E8E; font-style: italic; }
```

### 7.6 数据表格

```css
.data-table {
    width: 100%;
    border-collapse: collapse;
}

.data-table th {
    text-align: left;
    padding: 9px 14px;
    background: #F4F4F4;
    font-size: 11px;
    font-weight: 500;
    color: #8E8E8E;
    border-bottom: 1px solid #EEEEEE;
}

.data-table td {
    padding: 9px 14px;
    font-size: 12px;
    color: #393C41;
    border-bottom: 1px solid #EEEEEE;
}

.data-table tbody tr:hover td {
    background: #F4F4F4;
}
```

### 7.7 图表容器

```css
.chart-block {
    border-radius: 12px;
    overflow: hidden;
    background: #FFFFFF;
    margin: 12px 0;
    border: 1px solid #EEEEEE;
}

.chart-header {
    padding: 10px 14px;
    border-bottom: 1px solid #EEEEEE;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.chart-title {
    font-size: 13px;
    font-weight: 500;
    color: #171A20;
}

.chart-type-btns {
    display: flex;
    gap: 4px;
}

.chart-type-btn {
    height: 28px;
    padding: 0 10px;
    border-radius: 4px;
    border: 1px solid #D0D1D2;
    background: #FFFFFF;
    font-size: 11px;
    transition: all 0.33s;
}

.chart-type-btn.active {
    background: #171A20;
    border-color: #171A20;
    color: #FFFFFF;
}

.chart-container {
    height: 240px;
    padding: 8px 4px 12px;
}
```

### 7.8 加载状态

```css
.loading-indicator {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    background: #F4F4F4;
    border-radius: 4px;
}

.loading-dot {
    width: 5px; height: 5px;
    background: #3E6AE1;
    border-radius: 50%;
    animation: loadBounce 1.2s infinite ease-in-out both;
}

.loading-dot:nth-child(1) { animation-delay: -0.3s; }
.loading-dot:nth-child(2) { animation-delay: -0.15s; }
.loading-dot:nth-child(3) { animation-delay: 0s; }

@keyframes loadBounce {
    0%, 80%, 100% { transform: scale(0.7); opacity: 0.5; }
    40% { transform: scale(1); opacity: 1; }
}
```

### 7.9 模态框

```css
.modal-overlay {
    position: fixed;
    top: 0; left: 0;
    width: 100vw; height: 100vh;
    background: rgba(128, 128, 128, 0.65);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.33s, visibility 0.33s;
}

.modal-overlay.open {
    opacity: 1;
    visibility: visible;
}

.modal {
    width: 600px;
    max-height: 85vh;
    background: #FFFFFF;
    border-radius: 12px;
    overflow: hidden;
    transform: scale(0.98);
    transition: transform 0.33s;
    display: flex;
    flex-direction: column;
}

.modal-overlay.open .modal {
    transform: scale(1);
}
```

---

## 8. 布局结构

### 8.1 整体布局

```
┌─────────────────────────────────────────────────────────────────┐
│  SIDEBAR (220px)  │           MAIN CONTENT                    │
│  ┌─────────────┐   │  ┌─────────────────────────────────────┐ │
│  │ Logo        │   │  │ Header (48px)                        │ │
│  ├─────────────┤   │  │ - Title - Actions (btn, btn)        │ │
│  │ New Chat    │   │  ├─────────────────────────────────────┤ │
│  ├─────────────┤   │  │                                     │ │
│  │ History     │   │  │ Chat Container (flex: 1)             │ │
│  │ - Item 1   │   │  │ - Welcome Screen                    │ │
│  │ - Item 2   │   │  │ - Messages                          │ │
│  │ - ...      │   │  │   - User Message                     │ │
│  ├─────────────┤   │  │   - Assistant Message               │ │
│  │ Navigation │   │  │     - Steps Indicator                │ │
│  │ - Schema   │   │  │     - SQL Block                     │ │
│  │ - Settings │   │  │     - Chart Block                    │ │
│  └─────────────┘   │  │     - Data Table                    │ │
│                    │  ├─────────────────────────────────────┤ │
│                    │  │ Input Area (padding: 16px 24px)     │ │
│                    │  │ - Input Box + Send Button           │ │
│                    │  └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 响应式断点

| 断点 | 宽度 | 布局变化 |
|------|------|----------|
| Mobile | <768px | 侧边栏收起为抽屉，汉堡菜单触发 |
| Tablet | 768-1024px | 侧边栏 180px，聊天区域自适应 |
| Desktop | 1024-1440px | 完整布局，侧边栏 220px |
| Large Desktop | >1440px | 内容区域最大宽度 800px 居中 |

---

## 9. 功能页面

### 9.1 首页/聊天页

- **欢迎界面**：居中的欢迎语 + 快捷问题建议（2x2 网格）
- **消息列表**：用户/助手消息交替，带头像和气泡
- **消息区域**：包含 SQL 块、图表、数据表格的复合响应
- **输入区**：固定在底部，带发送按钮

### 9.2 Schema 浏览器页

- **搜索栏**：快速搜索表/字段
- **分类导航**：按数据库或功能分组
- **表详情**：表名、描述、列信息、关系图
- **枚举值展示**：状态字段的中文映射

### 9.3 设置页

- **标签页**：基础设置 / 数据库配置 / LLM 配置 / 安全设置
- **表单布局**：2 列网格，每组有标题
- **输入控件**：文本框、下拉选择、开关切换

---

## 10. 图标系统

### 10.1 图标风格

使用简洁的线条图标，stroke-width: 1.5-2px，与 Tesla 简洁风格保持一致。

### 10.2 常用图标

| 功能 | 图标 | 说明 |
|------|------|------|
| 新建聊天 | + | 蓝色主按钮 |
| 发送 | → | 箭头图标 |
| 复制 | ⎘ | 复制按钮 |
| 关闭 | × | 模态框关闭 |
| 设置 | ⚙ | 齿轮图标 |
| Schema | 📊 | 数据库图标 |
| 历史 | 🕐 | 时钟图标 |
| 加载 | ... | 三个点动画 |

---

## 11. 实现参考

### 11.1 CSS 变量定义

```css
:root {
    /* Brand */
    --blue: #3E6AE1;
    --blue-hover: #2F55B8;

    /* Surfaces */
    --white: #FFFFFF;
    --light-ash: #F4F4F4;
    --carbon: #171A20;
    --graphite: #393C41;
    --pewter: #5C5E62;
    --silver: #8E8E8E;
    --cloud: #EEEEEE;
    --pale-silver: #D0D1D2;

    /* Semantic */
    --success: #10B981;
    --warning: #F59E0B;
    --error: #EF4444;
    --info: #3E6AE1;

    /* Transitions */
    --t: 0.33s;

    /* Radius */
    --r-btn: 4px;
    --r-card: 12px;
}
```

### 11.2 原型文件参考

详细实现参考：`prototype.html`

该原型包含以下组件的完整实现：
- 侧边栏（Logo、导航、历史列表）
- 聊天界面（欢迎页、消息、输入框）
- SQL 代码高亮块
- 步骤指示器
- 图表容器（集成 ECharts）
- 数据表格
- 加载动画
- 设置模态框

---

## 12. 设计原则总结

### Do
- 使用 Electric Blue (#3E6AE1) 作为唯一的品牌强调色
- 保持按钮的 4px 微圆角
- 使用默认字间距（无负间距）
- 保持 0.33s 的统一过渡时间
- 让内容（数据、图表）成为视觉焦点
- 使用 #F4F4F4 作为微妙的背景区分

### Don't
- 不添加任何阴影（elevation 通过层级实现）
- 不使用渐变背景
- 不添加边框到卡片
- 不使用大圆角（超过 12px）
- 不在正文使用粗体或极细字重
- 不添加动画效果如 scale 或 translate

---

*本文档基于 Tesla Design System 灵感，结合 Micro-GenBI 数据分析平台的功能需求定制。详细实现请参考 `prototype.html` 原型文件。*
