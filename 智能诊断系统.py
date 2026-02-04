# 教案诊断系统.py
import os
import re
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
                content = content[first_newline+1:]
            # 去掉末尾的 ```
            if content.endswith("```"):
                content = content[:-3].strip()
        
        # 清洗2: 查找第一个 { 和最后一个 } 之间的内容（防止开头有文字说明）
        start_idx = content.find('{')
        end_idx = content.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            content = content[start_idx:end_idx+1]
        
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
    """调用大模型检测3个维度"""
    prompt = f"""
你是初中信息科技教案诊断专家。请严格基于以下【实际教案文本】进行分析，不要套用任何模板。

【强制要求】
1. 必须逐段阅读教案，识别真实的环节名称（支持变体：导入/引入/情境导入、新授/新课/知识讲解、练习/实践/探究、总结/小结/归纳、作业/作业布置/课后任务）
2. 必须提取每个环节的实际内容字数（包括子项列表内容）
3. 必须基于真实提取结果计算得分，禁止套用示例分数
4. 必须在"理由"字段引用原文片段作为证据

=== 1. 教学环节完整性（总分100分，5环节各20分）===
评分标准：
- 20分：环节名称明确（含变体），内容描述≥30字且有具体操作
- 10分：环节存在，但内容<30字或过于简略
- 0分：环节完全缺失（无任何相关表述）

输出字段：
- "score"：实际计算得分（各环节得分之和）
- "详情"：必须说明真实计算过程，如"导入环节'趣味导入'有效（20分），新授环节'知识新授'有效（20分），练习环节'实践探究'内容简略仅25字（10分），总结环节'总结归纳'有效（20分），作业环节未找到明确表述（0分），总分70分"
- "各环节状态"：数组，每个元素必须包含：
  * "环节"：标准映射名
  * "得分"：20/10/0（必须基于真实分析）
  * "是否存在"：true/false（true表示找到对应表述）
  * "内容有效"：true/false
  * "实际字数"：具体数字（用于验证≥30字标准）
  * "摘要"：该环节实际内容的概括（≤50字）
  * "原文引用"：从教案中摘录的该环节原文片段（作为证据）

=== 2. 时间分配合理性（总分100分）===
分析说明：从教案中提取各环节标注的时长（如"5分钟"、"10min"等）
评分：每有1个存在环节超出范围扣15分，总时长35-45分钟外扣20分

特殊规则：
- 若第1部分判定某环节缺失（得0分），则该环节"当前时长"=0，"建议时长"="环节缺失"，"是否合理"=false

输出字段：
- "score"：实际得分
- "建议"：每个环节包含：
  * "环节"：标准名
  * "当前时长"：提取的实际分钟数（0表示未提取到或环节缺失）
  * "建议时长"：参考范围或"环节缺失"
  * "是否合理"：true/false

=== 3. 核心素养匹配度（总分100分，四维均分）===
参照锚点：
【信息意识】优秀：对比验证信息来源；基础：辨别真伪；缺失：仅技能操作
【计算思维】优秀：问题分解+流程图；基础：按步骤操作；缺失：仅记忆
【数字化学习与创新】优秀：协作创作；基础：工具使用；缺失：无数字化
【信息社会责任】优秀：伦理讨论；基础：安全知识；缺失：无伦理

评分：每素养基于与锚点的语义相似度，按公式计算：优秀×0.5 + 基础×0.3 + (1-缺失)×0.2

输出字段：
- "avg_score"：四素养平均分（保留两位小数）
- "各素养"：每素养包含分数、相似度明细、匹配证据（引用原文）、理由

=== 输出格式要求 ===
严格JSON格式，不要添加markdown标记。必须基于【以下真实教案】分析，禁止假设或套用模板。

【待分析教案文本】：
{text}
"""
    return model_invocation(prompt)
def score_lesson_plan(diagnosis_result):
    """按权重计算三个维度的总分"""
    try:
        # 安全获取分数值（避免KeyError）
        section_score = diagnosis_result.get("环节完整性", {}).get("score", 0)
        time_score = diagnosis_result.get("时间分配", {}).get("score", 0)
        literacy_score = diagnosis_result.get("素养匹配", {}).get("avg_score", 0)  # 修正拼写：socre -> score

        # 加权计算：环节30% + 时间30% + 素养40%
        total_score = section_score * 0.3 + time_score * 0.3 + literacy_score * 0.4
        return round(total_score, 2)  # 保留2位小数
    except Exception as e:
        st.error(f"评分计算失败: {str(e)}")
        return 0.0
# ---------------------- 4. 图形化界面（上传+显示结果）----------------------
def Main_interface():
    st.set_page_config(page_title="智能诊断系统", layout="wide")
    st.title("📚 初中信息科技教案智能诊断系统")
    st.write("上传TXT教案文件，自动检测规范性并生成建议！")

    # 上传文件（仅支持TXT，避免PDF乱码）
    File_Upload = st.file_uploader("选择教案文件（TXT格式）", type=["txt"], key="uploader")

    if File_Upload:
        # 读取TXT内容（UTF-8编码防乱码）
        try:
            text = File_Upload.read().decode("utf-8")
        except:
            st.error("文件编码错误！请用记事本打开教案，另存为UTF-8格式TXT")
            return

        if len(text.strip()) < 100:
            st.warning("教案内容过短，可能无法准确检测！")
            return

        # 调用检测功能
        with st.spinner("大模型分析中...（约10秒）"):
            result = test_lesson_plan(text)

        # 显示结果
        st.subheader("📊 诊断结果（JSON格式）")
        st.json(result)  # 结构化展示
        # 计算总分
        total_score = score_lesson_plan(result)
        # 提取各维度分数
        section_score = result.get("环节完整性", {}).get("score", 0)
        time_score = result.get("时间分配", {}).get("score", 0)
        literacy_score = result.get("素养匹配", {}).get("avg_score", 0)
        # 显示分数卡片
        st.subheader("📈 教案评分")

        # 创建分数卡片布局
        col1, col2, col3, col4 = st.columns(4)

        # 环节完整性卡片
        col1.metric(
            label="环节完整性",
            value=f"{section_score}分",
            help="满分100分，评估导入/新授/练习/总结/作业5环节是否齐全有效"
        )

        # 时间分配卡片
        col2.metric(
            label="时间分配",
            value=f"{time_score}分",
            help="满分100分，评估各环节时长是否符合45分钟课程要求"
        )

        # 核心素养卡片
        col3.metric(
            label="核心素养",
            value=f"{literacy_score}分",
            help="满分100分，评估信息意识/计算思维等四大素养覆盖度"
        )

        # 总分卡片（突出显示）
        col4.metric(
            label="🏆 教案总分",
            value=f"{total_score}分",
            help="加权计算：环节30% + 时间30% + 素养40%"
        )

        # 添加进度条可视化
        st.progress(int(total_score), text=f"教案综合评分：{total_score}/100分")

                # 生成文字建议（直接调用API，不强制JSON格式）
        suggestions_prompt = f"根据诊断结果{result}，给老师写3条具体修改建议（简洁明了，用1. 2. 3.编号）："
        
        try:
            # 直接调用API，不经过model_invocation的JSON解析
            response = client.chat.completions.create(
                model="glm-4",
                messages=[{"role": "user", "content": suggestions_prompt}],
                temperature=0.7,  # 建议部分可以稍微有创意一些
                max_tokens=1000
            )
            text_suggestions = response.choices[0].message.content
        except Exception as e:
            text_suggestions = f"生成建议时出错：{str(e)}"
        
        st.subheader("💡 老师修改建议")
        st.info(text_suggestions)  # 蓝色背景突出显示


# ---------------------- 运行界面 ----------------------
if __name__ == "__main__":

    Main_interface()  # 启动图形界面







