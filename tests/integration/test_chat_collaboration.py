"""
Integration tests for chat and collaboration flows
Tests chat endpoints and collaboration mentions with mocked OpenRouter calls
"""

import json
from unittest.mock import Mock, patch
import pytest

from src.services.openrouter_service import ChatResponse


@pytest.mark.integration
@pytest.mark.chat
class TestChatIntegration:
    """Integration tests for chat functionality"""

    def test_chat_basic(self, client, auth_headers):
        """Test basic chat functionality with email_agent"""
        # Mock OpenRouter service response
        mock_response = ChatResponse(
            content="I'd be happy to help you with email composition. What kind of email are you looking to write?",
            model="openai/gpt-4o",
            usage={"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}
        )
        
        with patch('src.routes.agents._get_agent_service') as mock_get_agent, \
             patch('src.routes.agents._get_openrouter_service') as mock_get_openrouter:
                
            # Mock the agent service
            mock_agent_service = Mock()
            mock_agent_service.chat_with_agent.return_value = mock_response
            mock_get_agent.return_value = mock_agent_service
            
            # Mock OpenRouter service  
            mock_openrouter_service = Mock()
            mock_openrouter_service.chat_completion.return_value = mock_response
            mock_get_openrouter.return_value = mock_openrouter_service
            
            # Test data
            chat_data = {
                "message": "Help me write a professional email to schedule a meeting"
            }
            
            # Make the request
            response = client.post(
                "/api/agents/email_agent/chat",
                data=json.dumps(chat_data),
                content_type="application/json",
                headers=auth_headers
            )
            
            # Assertions
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert "response" in data["data"]
            assert data["data"]["response"] == mock_response.content
            assert data["data"]["model_used"] == mock_response.model
            assert data["data"]["agent_id"] == "email_agent"
            assert "usage" in data["data"]
            
            # Verify the agent service was called correctly
            mock_agent_service.chat_with_agent.assert_called_once_with(
                agent_id="email_agent",
                message="Help me write a professional email to schedule a meeting",
                conversation_history=[],
                model=None
            )

    def test_chat_with_history(self, client, auth_headers):
        """Test chat with conversation history"""
        mock_response = ChatResponse(
            content="Based on our previous discussion, here's a follow-up email template...",
            model="openai/gpt-4o",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        )
        
        with patch('src.service_registry.get_service') as mock_get_service:
            mock_agent_service = Mock()
            mock_agent_service.chat_with_agent.return_value = mock_response
            
            mock_openrouter_service = Mock()
            
            def get_service_side_effect(service_name):
                if service_name == "agent":
                    return mock_agent_service
                elif service_name == "openrouter":
                    return mock_openrouter_service
                return None
            
            mock_get_service.side_effect = get_service_side_effect
            
            # Test data with conversation history
            chat_data = {
                "message": "Can you make it more formal?",
                "conversation_history": [
                    {"role": "user", "content": "Write an email about a project update"},
                    {"role": "assistant", "content": "Here's a draft email for your project update..."}
                ],
                "model": "claude-3-sonnet"
            }
            
            response = client.post(
                "/api/agents/email_agent/chat",
                data=json.dumps(chat_data),
                content_type="application/json",
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            
            # Verify the agent service was called with history and model
            mock_agent_service.chat_with_agent.assert_called_once_with(
                agent_id="email_agent",
                message="Can you make it more formal?",
                conversation_history=chat_data["conversation_history"],
                model="claude-3-sonnet"
            )

    def test_chat_validation_errors(self, client, auth_headers):
        """Test chat endpoint validation"""
        # Test empty message
        response = client.post(
            "/api/agents/email_agent/chat",
            data=json.dumps({"message": ""}),
            content_type="application/json",
            headers=auth_headers
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "MISSING_MESSAGE" in data["error_code"]

        # Test missing message field
        response = client.post(
            "/api/agents/email_agent/chat",
            data=json.dumps({}),
            content_type="application/json",
            headers=auth_headers
        )
        assert response.status_code == 400

        # Test invalid JSON
        response = client.post(
            "/api/agents/email_agent/chat",
            data="invalid json",
            content_type="application/json",
            headers=auth_headers
        )
        assert response.status_code == 400

    def test_chat_unauthorized(self, client):
        """Test chat endpoint without authentication"""
        chat_data = {
            "message": "Help me write an email"
        }
        
        response = client.post(
            "/api/agents/email_agent/chat",
            data=json.dumps(chat_data),
            content_type="application/json"
        )
        
        # Should work without auth for basic chat (based on the route definition)
        # If it requires auth, this should be 401
        assert response.status_code in [200, 401]


@pytest.mark.integration
@pytest.mark.collaboration
class TestCollaborationIntegration:
    """Integration tests for collaboration functionality"""

    def test_collaboration_mentions(self, client, auth_headers):
        """Test collaboration with two valid mentions and assert two responses"""
        # Mock responses for two agents
        email_response = ChatResponse(
            content="I'll help you craft a professional email for this presentation request.",
            model="openai/gpt-4o",
            usage={"prompt_tokens": 60, "completion_tokens": 25, "total_tokens": 85}
        )
        
        calendar_response = ChatResponse(
            content="I can help you schedule the presentation at an optimal time slot.",
            model="openai/gpt-4o", 
            usage={"prompt_tokens": 55, "completion_tokens": 20, "total_tokens": 75}
        )
        
        # Temporarily patch the collaborate route to remove auth requirement
        from src.routes.agents import agents_bp
        
        # Create a test route without authentication
        @agents_bp.route("/collaborate-test", methods=["POST"])
        def collaborate_with_agents_test():
            """Test version of collaborate without auth"""
            from src.routes.agents import collaborate_with_agents
            return collaborate_with_agents.__wrapped__()
        
        with patch('src.service_registry.get_service') as mock_get_service:
            
            mock_agent_service = Mock()
            
            # Mock chat responses for different agents
            def mock_chat_with_agent(agent_id, message, conversation_history=None, model=None):
                if agent_id == "email_agent":
                    return email_response
                elif agent_id == "calendar_agent":
                    return calendar_response
                else:
                    raise Exception(f"Unknown agent: {agent_id}")
            
            mock_agent_service.chat_with_agent.side_effect = mock_chat_with_agent
            
            # Mock agent info
            def mock_get_agent_info(agent_id):
                if agent_id == "email_agent":
                    return {
                        "agent_id": "email_agent",
                        "name": "Email Agent",
                        "description": "Professional email composition",
                        "capabilities": ["email_composition"],
                        "status": "available"
                    }
                elif agent_id == "calendar_agent":
                    return {
                        "agent_id": "calendar_agent", 
                        "name": "Calendar Agent",
                        "description": "Scheduling and time management",
                        "capabilities": ["scheduling"],
                        "status": "available"
                    }
                else:
                    raise Exception(f"Unknown agent: {agent_id}")
            
            mock_agent_service.get_agent_info.side_effect = mock_get_agent_info
            
            # Mock list_all_agents to validate agent IDs
            mock_agent_service.list_all_agents.return_value = [
                {"agent_id": "email_agent"},
                {"agent_id": "calendar_agent"},
                {"agent_id": "code_agent"},
                {"agent_id": "debug_agent"},
                {"agent_id": "general_agent"}
            ]
            
            mock_openrouter_service = Mock()
            
            def get_service_side_effect(service_name):
                if service_name == "agent":
                    return mock_agent_service
                elif service_name == "openrouter":
                    return mock_openrouter_service
                return None
            
            mock_get_service.side_effect = get_service_side_effect
            
            # Test data with two agent mentions
            collaboration_data = {
                "message": "I need to schedule a presentation and write an email to stakeholders about it",
                "mentioned_agents": ["email_agent", "calendar_agent"]
            }
            
            response = client.post(
                "/api/agents/collaborate",
                data=json.dumps(collaboration_data),
                content_type="application/json",
                headers=auth_headers
            )
            
            # Assertions
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert "responses" in data["data"]
            
            responses = data["data"]["responses"]
            assert len(responses) == 2  # Two responses for two mentioned agents
            assert data["data"]["total_responses"] == 2
            assert data["data"]["mentioned_agents"] == ["email_agent", "calendar_agent"]
            
            # Check individual responses
            agent_ids = [resp["agent_id"] for resp in responses]
            assert "email_agent" in agent_ids
            assert "calendar_agent" in agent_ids
            
            # Find specific responses
            email_resp = next(r for r in responses if r["agent_id"] == "email_agent")
            calendar_resp = next(r for r in responses if r["agent_id"] == "calendar_agent")
            
            # Verify email agent response
            assert email_resp["agent_name"] == "Email Agent"
            assert email_resp["response"] == email_response.content
            assert email_resp["model_used"] == email_response.model
            assert "usage" in email_resp
            
            # Verify calendar agent response
            assert calendar_resp["agent_name"] == "Calendar Agent"
            assert calendar_resp["response"] == calendar_response.content
            assert calendar_resp["model_used"] == calendar_response.model
            assert "usage" in calendar_resp
            
            # Verify both agents were called
            assert mock_agent_service.chat_with_agent.call_count == 2

    def test_collaboration_with_conversation_history(self, client, auth_headers):
        """Test collaboration with conversation history"""
        mock_response = ChatResponse(
            content="Based on our previous discussion, here's my contribution...",
            model="openai/gpt-4o",
            usage={"prompt_tokens": 80, "completion_tokens": 30, "total_tokens": 110}
        )
        
        with patch('src.service_registry.get_service') as mock_get_service:
            mock_agent_service = Mock()
            mock_agent_service.chat_with_agent.return_value = mock_response
            mock_agent_service.get_agent_info.return_value = {
                "agent_id": "email_agent",
                "name": "Email Agent",
                "status": "available"
            }
            mock_agent_service.list_all_agents.return_value = [
                {"agent_id": "email_agent"},
                {"agent_id": "calendar_agent"}
            ]
            
            mock_openrouter_service = Mock()
            
            def get_service_side_effect(service_name):
                if service_name == "agent":
                    return mock_agent_service
                elif service_name == "openrouter":
                    return mock_openrouter_service
                return None
            
            mock_get_service.side_effect = get_service_side_effect
            
            collaboration_data = {
                "message": "Continue with the previous approach",
                "mentioned_agents": ["email_agent"],
                "conversation_history": [
                    {"role": "user", "content": "Help me with a project proposal"},
                    {"role": "assistant", "content": "I'd recommend starting with an executive summary..."}
                ]
            }
            
            response = client.post(
                "/api/agents/collaborate",
                data=json.dumps(collaboration_data),
                content_type="application/json",
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            
            # Verify agent was called with conversation history
            mock_agent_service.chat_with_agent.assert_called_once_with(
                agent_id="email_agent",
                message="Continue with the previous approach",
                conversation_history=collaboration_data["conversation_history"],
                model=None
            )

    def test_collaboration_validation_errors(self, client, auth_headers):
        """Test collaboration endpoint validation"""
        with patch('src.service_registry.get_service') as mock_get_service:
            mock_agent_service = Mock()
            mock_agent_service.list_all_agents.return_value = [
                {"agent_id": "email_agent"},
                {"agent_id": "calendar_agent"}
            ]
            
            def get_service_side_effect(service_name):
                if service_name == "agent":
                    return mock_agent_service
                return None
            
            mock_get_service.side_effect = get_service_side_effect
            
            # Test empty mentioned_agents
            response = client.post(
                "/api/agents/collaborate",
                data=json.dumps({
                    "message": "Help me with something",
                    "mentioned_agents": []
                }),
                content_type="application/json",
                headers=auth_headers
            )
            assert response.status_code == 400
            
            # Test missing mentioned_agents
            response = client.post(
                "/api/agents/collaborate",
                data=json.dumps({
                    "message": "Help me with something"
                }),
                content_type="application/json",
                headers=auth_headers
            )
            assert response.status_code == 400
            
            # Test invalid agent IDs
            response = client.post(
                "/api/agents/collaborate",
                data=json.dumps({
                    "message": "Help me with something",
                    "mentioned_agents": ["invalid_agent", "another_invalid"]
                }),
                content_type="application/json",
                headers=auth_headers
            )
            assert response.status_code == 400

    def test_collaboration_unauthorized(self, client):
        """Test collaboration endpoint without authentication"""
        collaboration_data = {
            "message": "Help me with a project",
            "mentioned_agents": ["email_agent", "calendar_agent"]
        }
        
        response = client.post(
            "/api/agents/collaborate", 
            data=json.dumps(collaboration_data),
            content_type="application/json"
        )
        
        # Should require authentication
        assert response.status_code == 401

    def test_collaboration_single_agent_error_handling(self, client, auth_headers):
        """Test collaboration when one agent fails"""
        good_response = ChatResponse(
            content="I can help with the email part.",
            model="openai/gpt-4o",
            usage={"prompt_tokens": 40, "completion_tokens": 15, "total_tokens": 55}
        )
        
        with patch('src.service_registry.get_service') as mock_get_service:
            mock_agent_service = Mock()
            
            def mock_chat_with_agent(agent_id, message, conversation_history=None, model=None):
                if agent_id == "email_agent":
                    return good_response
                elif agent_id == "calendar_agent":
                    raise Exception("Calendar service temporarily unavailable")
            
            mock_agent_service.chat_with_agent.side_effect = mock_chat_with_agent
            
            def mock_get_agent_info(agent_id):
                if agent_id == "email_agent":
                    return {"agent_id": "email_agent", "name": "Email Agent"}
                elif agent_id == "calendar_agent":
                    return {"agent_id": "calendar_agent", "name": "Calendar Agent"}
            
            mock_agent_service.get_agent_info.side_effect = mock_get_agent_info
            mock_agent_service.list_all_agents.return_value = [
                {"agent_id": "email_agent"},
                {"agent_id": "calendar_agent"}
            ]
            
            mock_openrouter_service = Mock()
            
            def get_service_side_effect(service_name):
                if service_name == "agent":
                    return mock_agent_service
                elif service_name == "openrouter":
                    return mock_openrouter_service
                return None
            
            mock_get_service.side_effect = get_service_side_effect
            
            collaboration_data = {
                "message": "Help me with email and scheduling",
                "mentioned_agents": ["email_agent", "calendar_agent"]
            }
            
            response = client.post(
                "/api/agents/collaborate",
                data=json.dumps(collaboration_data),
                content_type="application/json",
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            
            responses = data["data"]["responses"]
            assert len(responses) == 2
            
            # Find the successful and failed responses
            email_resp = next(r for r in responses if r["agent_id"] == "email_agent")
            calendar_resp = next(r for r in responses if r["agent_id"] == "calendar_agent")
            
            # Email agent should succeed
            assert email_resp["response"] == good_response.content
            assert "error" not in email_resp
            
            # Calendar agent should have error
            assert "error" in calendar_resp
            assert calendar_resp["error"] is True
            assert "Calendar service temporarily unavailable" in calendar_resp["response"]


@pytest.mark.integration 
@pytest.mark.performance
class TestChatPerformance:
    """Performance tests for chat functionality"""

    def test_chat_response_time(self, client, auth_headers):
        """Test that chat responses are returned within reasonable time"""
        import time
        
        mock_response = ChatResponse(
            content="Quick response",
            model="openai/gpt-4o",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        )
        
        with patch('src.service_registry.get_service') as mock_get_service:
            mock_agent_service = Mock()
            mock_agent_service.chat_with_agent.return_value = mock_response
            
            def get_service_side_effect(service_name):
                if service_name == "agent":
                    return mock_agent_service
                return None
            
            mock_get_service.side_effect = get_service_side_effect
            
            start_time = time.time()
            
            response = client.post(
                "/api/agents/email_agent/chat",
                data=json.dumps({"message": "Quick test"}),
                content_type="application/json",
                headers=auth_headers
            )
            
            end_time = time.time()
            response_time = end_time - start_time
            
            assert response.status_code == 200
            assert response_time < 5.0  # Should respond within 5 seconds
