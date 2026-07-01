from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage
from acnt_strat_synth.predict.tool import account_risk_score
from acnt_strat_synth.predict.score import score_account
from acnt_strat_synth.config import settings

llm = AzureChatOpenAI(
    azure_endpoint=settings.aoai_endpoint, api_key=settings.aoai_key,
    api_version=settings.aoai_api_version,
    azure_deployment=settings.chat_deployment, temperature=1,
).bind_tools([account_risk_score])

ai = llm.invoke([HumanMessage("Get the risk score for HCP-001 using the tool.")])
assert ai.tool_calls, f"no tool call: {ai}"
call = ai.tool_calls[0]
print("tool requested:", call["name"], call["args"])

tool_out = account_risk_score.invoke(call["args"])
print("tool output:", tool_out)
assert tool_out["risk_score"] == score_account("HCP-001")
print("ok")