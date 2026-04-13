import json
from pydantic import BaseModel
from typing import List, Dict, Optional
from synthetic_tooluse.schemas.graph import ChainPlan
from synthetic_tooluse.agents.base import BaseAgent

class UserResponse(BaseModel):
    content: str
    inferred_intent: str

class UserSimulator(BaseAgent):
    """Generates realistic user requests and responses to clarify intent."""
    
    def generate_initial_request(self, plan: ChainPlan) -> str:
        prompt = f"""
        You are a realistic user. Write an initial natural language request.
        Your True Intent is: {plan.intent_name}
        Context: {plan.intent_desc}
        Domains relevant to your question: {plan.target_domains}
        Make sure the query matches the intent exactly. Do not mention multiple random things.
        """
        
        messages = [{"role": "system", "content": prompt}]
        # simple hack to return string from fallback or structured logic
        resp = self(messages, response_format=UserResponse)
        if isinstance(resp, BaseModel):
            return resp.content
        return "Can you help me with a task?"
        
    def generate_reply(self, history: List[Dict[str, str]], plan: ChainPlan) -> str:
        prompt = "You are the user. Reply to the assistant's clarification naturally."
        messages = [{"role": "system", "content": prompt}] + history
        
        resp = self(messages, response_format=UserResponse)
        if isinstance(resp, BaseModel):
            return resp.content
        return "Sure, here is the information: 12345"
