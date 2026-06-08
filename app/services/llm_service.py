import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """Service for generating summaries with an external LLM."""

    @staticmethod
    async def summarize_text(text: str) -> str:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. Set it in your environment to enable LLM summaries."
            )

        max_length = 5000
        if len(text) > max_length:
            text = text[:max_length] + "\n\n[Truncated additional content for summarization]"

        prompt = (
            "Please summarize the following email content in a concise paragraph. "
            "Keep the summary factual, preserve the main points, and avoid adding new information.\n\n"
            f"Email content:\n{text}"
        )

        payload: dict[str, Any] = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that summarizes email content."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 300,
            "top_p": 1.0,
        }

        # Retry logic for transient API errors
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        settings.OPENAI_API_URL,
                        headers={
                            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )

                    # Handle rate limiting with retry
                    if response.status_code == 429:
                        import asyncio
                        wait_time = 2 ** attempt * 2  # 2, 4, 8 seconds
                        logger.warning(f"Rate limited (429), retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue

                    response.raise_for_status()
                    data = response.json()

                if not data or "choices" not in data or not data["choices"]:
                    raise RuntimeError("LLM did not return a valid summary response.")

                summary = data["choices"][0].get("message", {}).get("content")

                # Check for empty/whitespace content
                if not summary or not summary.strip():
                    logger.warning(f"LLM returned empty summary on attempt {attempt + 1}")
                    last_error = "LLM returned empty summary"
                    continue

                return summary.strip()

            except Exception as e:
                logger.error(f"LLM summarization error on attempt {attempt + 1}: {e}")
                last_error = str(e)
                # Don't retry on non-transient errors
                if "429" not in str(e):
                    raise
                continue

        # All retries failed
        raise RuntimeError(f"LLM summarization failed after {max_retries} attempts: {last_error}")

    @staticmethod
    async def classify_project_type(rag_content: str) -> dict:
        """
        Classify project as 'lead' or 'sale_opportunity' based on RAG content.
        
        Args:
            rag_content: Full RAG content to classify
            
        Returns:
            dict with 'type', 'confidence', and 'reasoning'
        """
        import json

        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. Set it in your environment to enable LLM classification."
            )

        max_length = 5000
        if len(rag_content) > max_length:
            rag_content = rag_content[:max_length] + "\n\n[Truncated for classification]"

        prompt = f"""Analyze the following email conversation content and classify the project as either:
- "lead": Initial inquiry, cold outreach, newsletter signup, general information request, no buying signals yet
- "sale_opportunity": Active deal, pricing discussions, contract negotiations, demos scheduled, budget discussions, decision-maker engagement, purchase intent

Provide your classification as JSON with these fields:
- type: "lead" or "sale_opportunity"
- confidence: a number between 0.0 and 1.0
- reasoning: brief explanation of your classification

Content to classify:
{rag_content}

Respond with valid JSON only, no other text."""

        payload: dict[str, Any] = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": "You are a sales analyst that classifies projects based on email content. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 200,
            "top_p": 1.0,
        }

        # Retry logic for transient API errors
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        settings.OPENAI_API_URL,
                        headers={
                            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )

                    # Handle rate limiting with retry
                    if response.status_code == 429:
                        import asyncio
                        wait_time = 2 ** attempt * 2  # 2, 4, 8 seconds
                        logger.warning(f"Rate limited (429), retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue

                    response.raise_for_status()
                    data = response.json()

                if not data or "choices" not in data or not data["choices"]:
                    raise RuntimeError("LLM did not return a valid classification response.")

                content = data["choices"][0].get("message", {}).get("content")

                # Check for empty/whitespace content
                if not content or not content.strip():
                    logger.warning(f"LLM returned empty content on attempt {attempt + 1}")
                    last_error = "LLM returned empty content"
                    continue

                # Parse JSON response
                content = content.strip()

                # Handle markdown code blocks (e.g., ```json ... ```)
                if content.startswith("```"):
                    lines = content.split("\n")
                    content = "\n".join(lines[1:-1])  # Remove first and last lines

                result = json.loads(content)

                # Validate required fields
                project_type = result.get("type", "lead")
                if project_type not in ("lead", "sale_opportunity"):
                    project_type = "lead"

                return {
                    "type": project_type,
                    "confidence": float(result.get("confidence", 0.5)),
                    "reasoning": result.get("reasoning", ""),
                }

            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse error on attempt {attempt + 1}: {e}")
                logger.warning(f"Raw content: {content[:200] if content else 'None'}")
                last_error = f"JSON parse error: {str(e)}"
                continue

            except Exception as e:
                logger.error(f"LLM classification error on attempt {attempt + 1}: {e}")
                last_error = str(e)
                continue

        # All retries failed - use fallback
        logger.error(f"All {max_retries} attempts failed. Last error: {last_error}")
        return {
            "type": "lead",
            "confidence": 0.0,
            "reasoning": f"Classification failed after {max_retries} attempts: {last_error}",
        }

    @staticmethod
    async def generate_project_name(summary: str) -> str:
        """
        Generate a short, descriptive project name from summary.
        
        Args:
            summary: Document summary to generate name from
            
        Returns:
            Project name (max 100 chars)
        """
        if not settings.OPENAI_API_KEY:
            # Fallback: use first 50 chars of summary
            return summary[:50].strip() + "..." if len(summary) > 50 else summary

        prompt = f"""Generate a short, descriptive project name (max 50 characters) for an email conversation with this summary:

{summary}

Respond with only the project name, no quotes or other text."""

        payload: dict[str, Any] = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": "You generate short, descriptive project names. Respond with only the name."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 50,
            "top_p": 1.0,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                settings.OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        if not data or "choices" not in data or not data["choices"]:
            # Fallback
            return summary[:50].strip() + "..." if len(summary) > 50 else summary

        name = data["choices"][0].get("message", {}).get("content")
        if not name:
            return summary[:50].strip() + "..." if len(summary) > 50 else summary

        # Clean up the name
        name = name.strip().strip('"').strip("'")
        if len(name) > 100:
            name = name[:100]

        return name

    @staticmethod
    async def analyze_bant_component(rag_content: str, component: str) -> str:
        """
        Analyze a single BANT component from RAG content.
        
        Args:
            rag_content: Full RAG content to analyze
            component: BANT component to analyze ("budget", "authority", "need", "timeline")
            
        Returns:
            Text analysis of the component
        """
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. Set it in your environment to enable LLM analysis."
            )

        max_length = 5000
        if len(rag_content) > max_length:
            rag_content = rag_content[:max_length] + "\n\n[Truncated for analysis]"

        prompts = {
            "budget": """Analyze the following email conversation for BUDGET information.

Look for:
- Budget mentions, allocations, or constraints
- Pricing discussions or cost sensitivity
- Funding availability or budget approval status
- Price objections or value negotiations
- Expected investment range or spending plans

Provide a detailed text analysis (2-4 paragraphs) covering what you found about the budget.
If no budget information is found, state "No budget information discussed yet."

Content to analyze:
{content}

Respond with the analysis text only, no JSON formatting.""",

            "authority": """Analyze the following email conversation for AUTHORITY information.

Look for:
- Decision-maker identification (titles, roles)
- Organizational hierarchy and approval process
- Who has purchasing authority
- Whether the contact can make final decisions
- Need for additional approvals or stakeholders

Provide a detailed text analysis (2-4 paragraphs) covering what you found about authority.
If no authority information is found, state "No authority information identified yet."

Content to analyze:
{content}

Respond with the analysis text only, no JSON formatting.""",

            "need": """Analyze the following email conversation for NEED information.

Look for:
- Pain points or challenges mentioned
- Specific requirements or use cases
- Business problems they want to solve
- Urgency indicators or critical needs
- Current solution gaps or frustrations

Provide a detailed text analysis (2-4 paragraphs) covering what you found about their needs.
If no need information is found, state "No specific needs discussed yet."

Content to analyze:
{content}

Respond with the analysis text only, no JSON formatting.""",

            "timeline": """Analyze the following email conversation for TIMELINE information.

Look for:
- Implementation deadlines or target dates
- Urgency indicators
- Go-live expectations
- Project phases or milestones
- Decision timelines or approval schedules

Provide a detailed text analysis (2-4 paragraphs) covering what you found about timeline.
If no timeline information is found, state "No timeline information discussed yet."

Content to analyze:
{content}

Respond with the analysis text only, no JSON formatting.""",
        }

        prompt = prompts[component].format(content=rag_content)

        payload: dict[str, Any] = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": f"You are a sales analyst specializing in BANT qualification. Analyze the {component} aspect of the sales conversation."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 500,
            "top_p": 1.0,
        }

        # Retry logic for transient API errors
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        settings.OPENAI_API_URL,
                        headers={
                            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )

                    # Handle rate limiting with retry
                    if response.status_code == 429:
                        import asyncio
                        wait_time = 2 ** attempt * 2
                        logger.warning(f"Rate limited (429), retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue

                    response.raise_for_status()
                    data = response.json()

                if not data or "choices" not in data or not data["choices"]:
                    raise RuntimeError(f"LLM did not return a valid {component} response.")

                content = data["choices"][0].get("message", {}).get("content")

                # Check for empty/whitespace content
                if not content or not content.strip():
                    logger.warning(f"LLM returned empty {component} analysis on attempt {attempt + 1}")
                    last_error = f"LLM returned empty {component} analysis"
                    continue

                return content.strip()

            except Exception as e:
                logger.error(f"LLM {component} analysis error on attempt {attempt + 1}: {e}")
                last_error = str(e)
                if "429" not in str(e):
                    raise
                continue

        # All retries failed
        raise RuntimeError(f"LLM {component} analysis failed after {max_retries} attempts: {last_error}")

    @staticmethod
    async def analyze_bant(rag_content: str) -> dict:
        """
        Analyze all BANT components from RAG content.
        
        Args:
            rag_content: Full RAG content to analyze
            
        Returns:
            dict with 'budget', 'authority', 'need', 'timeline', and 'summary' keys
        """
        # Analyze each component
        budget = await LLMService.analyze_bant_component(rag_content, "budget")
        authority = await LLMService.analyze_bant_component(rag_content, "authority")
        need = await LLMService.analyze_bant_component(rag_content, "need")
        timeline = await LLMService.analyze_bant_component(rag_content, "timeline")

        # Generate overall summary
        summary_prompt = f"""Based on the following BANT analysis, provide a brief overall summary (2-3 sentences) of the sales opportunity quality.

Budget: {budget}

Authority: {authority}

Need: {need}

Timeline: {timeline}

Provide a concise summary of the overall BANT qualification status."""

        payload: dict[str, Any] = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": "You are a sales analyst providing BANT qualification summaries."},
                {"role": "user", "content": summary_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 200,
            "top_p": 1.0,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                settings.OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        if not data or "choices" not in data or not data["choices"]:
            summary = f"Budget: {budget[:100]}... Authority: {authority[:100]}... Need: {need[:100]}... Timeline: {timeline[:100]}..."
        else:
            summary = data["choices"][0].get("message", {}).get("content", "")
            if not summary:
                summary = f"Budget: {budget[:100]}... Authority: {authority[:100]}... Need: {need[:100]}... Timeline: {timeline[:100]}..."

        return {
            "budget": budget,
            "authority": authority,
            "need": need,
            "timeline": timeline,
            "summary": summary.strip(),
        }
