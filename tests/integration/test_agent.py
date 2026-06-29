# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest.mock import patch

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.agent import root_agent


def mock_get_articles(topic: str) -> str:
    return """
Article #1
Title: Congress debates sweeping AI regulation bill to curb deepfakes
Source: CNN
URL: https://www.cnn.com/2026/06/21/tech/ai-bill-congress/index.html
Date: 2026-06-21T14:30:00Z
Content Snippet: Lawmakers are debating a new bipartisan bill targeting AI-generated deepfakes and intellectual property protections. Proponents argue it is crucial to protect artists and prevent misinformation, while some tech lobby groups warn it could stifle innovation in open-source AI models.
---
Article #2
Title: Silicon Valley pushes back on heavy-handed AI rules, warns of losing competitive edge
Source: Fox News
URL: https://www.foxnews.com/tech/silicon-valley-ai-regulation-pushback
Date: 2026-06-22T09:15:00Z
Content Snippet: Tech entrepreneurs and conservative lawmakers are expressing alarm over the proposed AI regulation bill, calling it a regulatory overreach that benefits large tech monopolies while killing startup competition. They argue that innovation should be market-driven rather than choked by federal bureaucracy.
---
Article #3
Title: Inside the grassroots campaign to regulate AI and protect independent creators
Source: Democracy Now
URL: https://www.democracynow.org/2026/06/23/grassroots_ai_regulation
Date: 2026-06-23T11:00:00Z
Content Snippet: A coalition of writers, artists, and independent creators have petitioned Congress to include strict copyright protections in the upcoming AI bill. Activists point out that mainstream media conglomerates are signing licensing deals with AI companies, leaving independent creators vulnerable to exploitation.
---
Article #4
Title: Global markets brace for new AI compliance standards as EU-US pact looms
Source: Reuters
URL: https://www.reuters.com/technology/global-markets-ai-standards-eu-us-2026-06-23/
Date: 2026-06-23T16:00:00Z
Content Snippet: Analysts predict a shift in global tech investment as the US and EU discuss aligned regulatory standards for high-risk AI models. Corporate compliance costs are expected to rise, prompting concerns among venture capitalists, though trade representatives claim standardized rules will foster long-term stability.
---
Article #5
Title: Why the proposed AI regulation bill will entrench tech monopolies
Source: Reason Magazine
URL: https://reason.com/2026/06/24/proposed-ai-regulation-entrench-monopolies/
Date: 2026-06-24T10:00:00Z
Content Snippet: The proposed AI licensing framework creates massive barriers to entry for independent developers. By requiring costly audits and compliance officers, Congress is effectively cartelizing the tech industry, locking out startup competitors, and protecting established tech monopolies from market disruption.
---
Article #6
Title: Regulators warn failing to establish AI guardrails threatens core democratic institutions
Source: Associated Press
URL: https://apnews.com/article/regulators-warn-failing-ai-guardrails-threatens-democracy
Date: 2026-06-24T12:00:00Z
Content Snippet: Federal election officials and cybersecurity directors released a joint warning outlining how unregulated AI-generated audio and video deepfakes pose immediate risks to election integrity. They urged lawmakers to establish baseline legal rules to verify political advertising sources before the upcoming voting cycle.
"""


@patch("agents.search_agent.get_live_news_articles", side_effect=mock_get_articles)
def test_agent_stream(mock_search) -> None:
    """
    Integration test for the agent stream functionality.
    Tests that the agent returns valid streaming responses.
    """

    session_service = InMemorySessionService()

    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(
        role="user",
        parts=[
            types.Part.from_text(
                text="Proposed sweeping AI regulation bill and deepfakes"
            )
        ],
    )

    events = list(
        runner.run(
            new_message=message,
            user_id="test_user",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        )
    )
    assert len(events) > 0, "Expected at least one message"

    has_text_content = False
    for event in events:
        if (
            event.content
            and event.content.parts
            and any(part.text for part in event.content.parts)
        ):
            has_text_content = True
            break
    assert has_text_content, "Expected at least one message with text content"
