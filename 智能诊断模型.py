# 教案诊断系统.py
import streamlit as st
from zhipuai import ZhipuAI  # 智谱GLM-4库
import json

# ---------------------- 1. 配置大模型（智谱GLM-4）----------------------
API_KEY = st.secrets["api_key"]
client = ZhipuAI(api_key=API_KEY)


# ---------------------- 2. 大模型调用函数----------------------
def model_invocation(prompt):
    """用智谱GLM-4分析教案，返回解析后的字典，增强容错处理"""
    try:
        response = client.chat.completions.create(
            model="glm-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000
        )
        content = response.choices[0].message.content

        # 保存原始响应以便调试
        raw_content = content

        # 清洗1: 去除 Markdown 代码块标记 (```json ... ```)
        content = content.strip()
        if content.startswith("```"):
            # 找到第一个换行符，去掉第一行(```json)
            first_newline = content.find('\n')
            if first_newline != -1:
                content = content[first_newline + 1:]
            # 去掉末尾的 ```
            if content.endswith("```"):
                content = content[:-3].strip()

        # 清洗2: 查找第一个 { 和最后一个 } 之间的内容（防止开头有文字说明）
        start_idx = content.find('{')
        end_idx = content.rfind('}')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            content = content[start_idx:end_idx + 1]

        # 清洗3: 去除首尾空白
        content = content.strip()

        # 尝试解析
        return json.loads(content)

    except json.JSONDecodeError as e:
        # 如果还是失败，返回包含原始内容的错误信息，方便调试
        return {
            "error": "大模型返回内容不是合法JSON格式",
            "解析错误": str(e),
            "原始内容前200字": raw_content[:200] if 'raw_content' in locals() else "无",
            "清洗后内容前200字": content[:200] if 'content' in locals() else "无"
        }
    except Exception as e:
        return {"error": f"调用大模型失败：{str(e)}"}


# ---------------------- 3. 教案检测核心功能----------------------
def test_lesson_plan(text):
    """分三步调用，降低单次token消耗，提高准确性"""

    # 第一步：环节完整性检测（精简版）
    step1_result = check_completeness(text)

    # 第二步：时间分配检测（基于step1结果）
    step2_result = check_time_allocation(text, step1_result)

    # 第三步：素养匹配检测（独立进行）
    step3_result = check_literacy(text)

    # 合并结果
    return {
        "环节完整性": step1_result,
        "时间分配": step2_result,
        "素养匹配": step3_result
    }


def check_completeness(text):
    """环节完整性检测 - 修复评分计算逻辑，增加强制验证"""
    # 用分隔符包裹教案内容，隔离特殊字符
    text_wrapped = f"```\n{text}\n```"
    prompt = f"""你是初中信息科技教案诊断专家，严格按规则检测教学环节完整性，必须精准计算分数。

【5环节识别关键词】
导入：导入/引入/情境导入/问题导入/激趣导入/开场
新授：新授/新课/讲授/讲解/知识讲解/新知探究
练习：练习/实践/活动/探究活动/动手实践/巩固练习/小组探究/实操
总结：总结/小结/课堂总结/归纳/知识梳理/回顾
作业：作业/作业布置/课后作业/课堂作业/家庭作业/拓展作业/课后练习/课后任务/布置作业/课后延伸/课外作业/五、作业/六、作业

【检测规则】
1. 逐段扫描全文，合并分散的同类活动
2. 作业环节重点检查：教案末尾、编号段落（五、六、七）
3. 该环节对应的内容字数≥30字且有具体操作步骤=内容有效

【评分规则（强制遵守）】
- 总分计算：初始总分0，每环节独立计分后累加，总分范围0-100
- 单环节计分标准：
  完整（内容有效）：20分
  存在但简略（<30字/无具体操作）：10分
  缺失：0分
- 计算示例：导入20 + 新授20 + 练习10 + 总结20 + 作业0 = 70分（此示例仅作计算参考）

【输出要求】
1. 必须严格按单环节计分标准计算，总分=各环节得分之和
2. 缺失环节列表仅包含得0分的环节
3. 输出JSON格式必须符合要求，不得篡改结构

输出JSON：
{{
"各环节状态": [
  {{"环节":"导入","得分":20,"是否存在":true,"内容有效":true,"摘要":"..."}},
  {{"环节":"新授","得分":20,"是否存在":true,"内容有效":true,"摘要":"..."}},
  {{"环节":"练习","得分":10,"是否存在":true,"内容有效":false,"摘要":"..."}},
  {{"环节":"总结","得分":20,"是否存在":true,"内容有效":true,"摘要":"..."}},
  {{"环节":"作业","得分":0,"是否存在":false,"内容有效":false,"摘要":""}}
],
"详情": "扣分说明（需明确每个扣分环节的扣分原因和分值）",
"缺失环节": ["作业"]或[],
"score": "0-100"
}}
【最后强制指令】
1. 分数必须一步一步算完再输出
2. 禁止为各环节得分预设固定值，必须根据教案内容判定
3. 禁止将计算结果四舍五入凑整
4. 自检标准：
   - 总分=各环节得分之和
   - 单环节得分只能是0/10/20
   - 缺失环节列表仅包含得0分的环节
5. 自检不通过则重新计算

教案内容：
{text_wrapped}
"""
    # 直接调用优化后的model_invocation函数
    return model_invocation(prompt)
def check_time_allocation(text, completeness_result):
    """时间分配检测 - 修复分数固化问题，明确总分计算逻辑"""
    # 1. 严格校验输入参数
    if not completeness_result or "各环节状态" not in completeness_result:
        return {"error": "完整性检测结果格式错误，无法进行时间分配检测"}
    # 提取环节存在情况
    existing = [s["环节"] for s in completeness_result.get("各环节状态", []) if s.get("是否存在")]

    # 2. 分隔符包裹教案内容
    text_wrapped = f"```\n{text}\n```"
    prompt = f"""你是教案时间分析专家，严格按规则检测时间分配合理性，分数必须动态计算，不得固定值。

【已确认存在的环节】{existing}
【总课时】40分钟

【时间推断规则】无明确标注时智能推断：
- 导入：简单提问（关键词：提问、问答）→3min，多媒体（关键词：图片、视频、PPT）→5min，复杂情境（关键词：情境、故事、案例）→7min
- 新授：1-2概念（关键词：概念、定义）→12-15min，3-4知识点（关键词：知识点、要点）→18-22min，复杂+互动（关键词：互动、讨论、小组）→23-25min  
- 练习：简单操作（关键词：操作、演示）→5-8min，小组讨论（关键词：小组、讨论）→10-12min，复杂项目（关键词：项目、任务）→15-18min
- 总结：教师总结（关键词：教师、总结）→2min，互动（关键词：互动、问答）→3min，学生归纳（关键词：学生、归纳）→4-5min
- 作业：简单题目（关键词：题目、习题）→2min，实践任务（关键词：实践、任务）→3-4min

【合理范围（强制判定）】
- 导入：2-6min | 新授：10-25min | 练习：5-18min | 总结：1-5min | 作业：1-4min
- 核心补充：不存在的环节时长为0，0分钟不属于任何环节的合理范围，需按规则扣分

【评分规则（强制执行，一步都不能漏）】
1. 初始总分：100分
2. 扣分规则（累计扣分，最低0分）：
   - 单个环节时长超出合理范围（含缺失环节时长0）：扣10分/个（所有环节都要检查，无论是否存在）
   - 总时长＞50分钟 或 总时长＜40分钟：扣15分（仅扣一次）
3. 总分计算：100 - 累计扣分（示例参考：导入超时扣10 + 作业缺失扣10 + 总时长低扣15 = 累计扣35 → 总分100-36=65）

【输出格式要求】
1. "当前时长"标注来源：X分钟[原文标注] 或 X分钟[推断：依据...] 或 0[环节缺失]
2. 必须先计算各环节时长→判断是否合理→计算累计扣分→得出总分
3. 扣分详情需包含：各环节时长推断依据、扣分项、总分计算过程
4. 分数不得固定为85/75等，必须根据教案内容动态计算

输出JSON：
{{
"各环节时长详情": [
  {{"环节":"导入","当前时长":"5分钟[原文标注]","建议时长":"1-7分钟","是否合理":true}},
  {{"环节":"新授","当前时长":"22分钟[推断：3个知识点+演示]","建议时长":"10-25分钟","是否合理":true}},
  ...
],
"扣分详情": "含推断逻辑+扣分说明+总分计算过程",
"score": "0-100（必须为计算结果）"
}}
【最后强制指令】
1. 分数必须一步一步算完再输出
2. 禁止预设固定分数（如85、75）
3. 禁止凑整、禁止瞎编时长和分数
4. 结果不对就重新算（自检标准：累计扣分=各环节超时分+总时长扣分；总分=100-累计扣分；score≥0且≤100）

教案内容：
{text_wrapped}
"""
    return model_invocation(prompt)

def check_literacy(text):
    """素养匹配检测 - 简化计算逻辑，增加示例强制验证"""
    # 分隔符包裹教案内容
    text_wrapped = f"```\n{text}\n```"
    prompt = f"""你是核心素养评估专家，用锚点对比法评估四维素养，必须严格按公式计算分数。

【锚点对比法（强制执行）】
Step 1: 三级语义匹配
- 对每个素养，计算教案文本与「优秀、基础、缺失」三个锚点的语义相似度（记为E、B、L）；
- 约束：E + B + L = 1.0（校验和），每个值范围为0~1；
- 匹配度越高，代表教案文本越贴近该锚点的素养要求。

Step 2: 得分计算（必须按此公式，不得篡改）
- 单素养得分 = (优秀匹配度×1.0 + 基础匹配度×0.6 + 缺失匹配度×0.2) × 100
  （权重逻辑：优秀=1.0（高阶素养）、基础=0.6（达标素养）、缺失=0.2（最低阶），分数范围0~100分）；
- 四素养平均分 = (信息意识得分 + 计算思维得分 + 数字化学习与创新得分 + 信息社会责任得分) / 4

【四维锚点】
信息意识：
- 优秀：感知技术对社会生活的影响，主动探究知识，树立数据安全与自主解决问题的意识
- 基础：了解基本概念，辨别网络信息真伪，培养甄别意识
- 缺失：仅学习使用搜索引擎

计算思维：
- 优秀：任务分解为步骤，绘制流程图，描述算法逻辑,理解问题解决过程
- 基础：按步骤完成操作，理解问题解决过程
- 缺失：仅记住操作步骤

数字化学习与创新：
- 优秀：小组协作在线文档，插入多媒体，在线演示，根据学习需求选择不同的数字设备进行自主学习
- 基础：利用Word制作小报，整合网络资料
- 缺失：仅阅读课本内容

信息社会责任：
- 优秀：讨论分析人工智能的利与弊，遵守信息科技领域的伦理道德规范，能正确应用人工智能技术等
- 基础：了解网络安全，不泄露个人信息
- 缺失：仅学习软件操作技巧

输出JSON：
{{
"各素养": {{
  "信息意识": {{
    "匹配值": {{"优秀":0.X,"基础":0.X,"缺失":0.X,"校验和":1.0}},
    "计算": "单素养得分=（优秀×1.0 + 基础×0.6 + 缺失×0.2）×100 = (0.X×1.0 + 0.X×0.6 + 0.X×0.2)×100 = X分",
    "得分": "X（必须与计算结果一致）",
    "证据": ["..."],
    "理由": "..."
  }},
  "计算思维": {{...}},
  "数字化学习与创新": {{...}},
  "信息社会责任": {{...}}
}},
"avg_score": "四素养平均分",
}}
【自检】输出前确认：
1、每个素养：优秀匹配+基础匹配+缺失匹配=1.0
2、每个素养：得分=(优秀×1.0+基础×0.6+缺失×0.2)×100
3、avg_score=(四素养得分之和)/4，取两位小数
4、所有"得分"必须与"计算过程"结果完全一致
5、匹配值示例：信息意识-优秀=0.7、基础=0.2、缺失=0.1（校验和=1.0），计算=(0.7×1.0+0.2×0.6+0.1×0.2)×100=84.0分

教案内容：
{text_wrapped}
"""
    return model_invocation(prompt)

def score_lesson_plan(diagnosis_result):
    """按权重计算三个维度的总分"""
    try:
        def safe_get_score(data, *keys, default=0):
            try:
                for key in keys:
                    if not isinstance(data, dict):
                        return default
                    data = data.get(key, {})
                if isinstance(data, str):
                    import re
                    numbers = re.findall(r'\d+\.?\d*', data)
                    return float(numbers[0]) if numbers else default
                return float(data) if data is not None else default
            except:
                return default

        section_score = safe_get_score(diagnosis_result, "环节完整性", "score")
        time_score = safe_get_score(diagnosis_result, "时间分配", "score")
        literacy_score = safe_get_score(diagnosis_result, "素养匹配", "avg_score")

        total_score = section_score * 0.3 + time_score * 0.3 + literacy_score * 0.4
        return round(total_score, 2)
    except Exception as e:
        st.error(f"评分计算失败: {str(e)}")
        return 0.0


# ---------------------- 4. 图形化界面（上传+显示结果）----------------------
def Main_interface():
    st.set_page_config(page_title="智能诊断系统", layout="wide")
    st.title("📚 初中信息科技教案智能诊断系统")
    st.write("上传TXT教案文件，自动检测规范性并生成建议！")

    File_Upload = st.file_uploader("选择教案文件（TXT格式）", type=["txt"], key="uploader")

    if File_Upload:
        try:
            text = File_Upload.read().decode("utf-8")
        except:
            st.error("文件编码错误！请用记事本打开教案，另存为UTF-8格式TXT")
            return

        if len(text.strip()) < 100:
            st.warning("教案内容过短，可能无法准确检测！")
            return

        # 调用检测功能（添加错误处理）
        with st.spinner("大模型分析中...（约需15-20秒，分三步检测）"):
            try:
                result = test_lesson_plan(text)
            except Exception as e:
                st.error(f"诊断过程出错：{str(e)}")
                return

        # 显示结果
        st.subheader("📊 诊断结果（JSON格式）")
        st.json(result)

        # 计算总分
        total_score = score_lesson_plan(result)

        # 安全提取各维度分数
        section_score = result.get("环节完整性", {}).get("score", 0) or 0
        time_score = result.get("时间分配", {}).get("score", 0) or 0
        literacy_score = result.get("素养匹配", {}).get("avg_score", 0) or 0

        # 显示分数卡片
        st.subheader("📈 教案评分")
        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            label="环节完整性",
            value=f"{section_score}分",
            help="满分100分，评估导入/新授/练习/总结/作业5环节是否齐全有效"
        )
        col2.metric(
            label="时间分配",
            value=f"{time_score}分",
            help="满分100分，评估各环节时长是否符合45分钟课程要求"
        )
        col3.metric(
            label="核心素养",
            value=f"{literacy_score}分",
            help="满分100分，评估信息意识/计算思维等四大素养覆盖度"
        )
        col4.metric(
            label="🏆 教案总分",
            value=f"{total_score}分",
            help="加权计算：环节30% + 时间30% + 素养40%"
        )

        st.progress(int(total_score), text=f"教案综合评分：{total_score}/100分")

        # 生成文字建议
        suggestions_prompt = f"根据诊断结果{result}，给老师写3条具体修改建议（简洁明了，用1. 2. 3.编号）："

        try:
            response = client.chat.completions.create(
                model="glm-4",
                messages=[{"role": "user", "content": suggestions_prompt}],
                temperature=0.7,
                max_tokens=1000
            )
            text_suggestions = response.choices[0].message.content
        except Exception as e:
            text_suggestions = f"生成建议时出错：{str(e)}"

        st.subheader("💡 老师修改建议")
        st.info(text_suggestions)


# ---------------------- 运行界面 ----------------------
if __name__ == "__main__":
    Main_interface()