#!/usr/bin/env python3
"""
Splitwise MCP Server

A Model Context Protocol server for Splitwise expense management.
Provides tools for managing expenses, users, and groups in Splitwise.
"""

import os
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Context
from pydantic import BaseModel
import logging
from dotenv import load_dotenv

load_dotenv()

# Splitwise API base URL
SPLITWISE_API_BASE = "https://secure.splitwise.com/api/v3.0"

# Initialize MCP server
mcp = FastMCP("Splitwise")

logger = logging.getLogger(__name__)

@dataclass
class SplitwiseConfig:
    """Configuration for Splitwise API"""
    consumer_key: Optional[str] = None
    consumer_secret: Optional[str] = None
    access_token: Optional[str] = None
    api_key: Optional[str] = None


class SplitwiseUser(BaseModel):
    """Splitwise user model"""
    id: int
    first_name: str
    last_name: Optional[str] = None
    email: Optional[str] = None
    registration_status: Optional[str] = None
    picture: Optional[Dict[str, str]] = None


class SplitwiseGroup(BaseModel):
    """Splitwise group model"""
    id: int
    name: str
    created_at: str
    updated_at: str
    members: List[SplitwiseUser]
    simplify_by_default: bool
    original_debts: List[Dict[str, Any]]
    simplified_debts: List[Dict[str, Any]]


class SplitwiseExpense(BaseModel):
    """Splitwise expense model"""
    id: int
    group_id: int
    description: str
    payment: bool
    cost: str
    currency_code: str
    date: str
    created_at: str
    updated_at: str
    created_by: SplitwiseUser
    updated_by: SplitwiseUser
    category: Dict[str, Any]
    details: Optional[str] = None
    users: List[Dict[str, Any]]
    expense_bundle_id: Optional[int] = None
    friendship_id: Optional[int] = None
    repayments: List[Dict[str, Any]]


class SplitwiseClient:
    """Client for interacting with Splitwise API"""
    
    def __init__(self, config: SplitwiseConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=SPLITWISE_API_BASE,
            timeout=30.0
        )
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        if self.config.api_key:
            return {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
        else:
            # For OAuth, we'd need to implement the OAuth flow
            # For now, we'll require an API key
            raise ValueError("API key is required. OAuth flow not implemented yet.")
    
    async def get_current_user(self) -> SplitwiseUser:
        """Get current user information"""
        response = await self.client.get(
            "/get_current_user",
            headers=self._get_headers()
        )
        response.raise_for_status()
        data = response.json()
        
        if response.status_code != 200:
            raise ValueError(f"API request failed: {data.get('errors', 'Unknown error')}")
        
        return SplitwiseUser(**data["user"])
    
    async def get_groups(self) -> List[SplitwiseGroup]:
        """Get all groups for the current user"""
        response = await self.client.get(
            "/get_groups",
            headers=self._get_headers()
        )
        response.raise_for_status()
        data = response.json()
        
        if response.status_code != 200:
            raise ValueError(f"API request failed: {data.get('errors', 'Unknown error')}")
        
        return [SplitwiseGroup(**group) for group in data["groups"]]
    
    async def get_friends(self) -> List[SplitwiseUser]:
        """Get all friends for the current user"""
        response = await self.client.get(
            "/get_friends",
            headers=self._get_headers()
        )
        response.raise_for_status()
        data = response.json()
        
        if response.status_code != 200:
            raise ValueError(f"API request failed: {data.get('errors', 'Unknown error')}")
        
        return [SplitwiseUser(**friend) for friend in data["friends"]]
    
    async def create_expense(
        self,
        cost: str,
        description: str,
        group_id: Optional[int] = None,
        users: Optional[List[Dict[str, Any]]] = None,
        currency_code: str = "USD",
        date: Optional[str] = None,
        details: Optional[str] = None,
        payment: bool = False,
        category_id: Optional[int] = None
    ) -> SplitwiseExpense:
        """Create a new expense with user splitting support"""
        payload = {
            "cost": cost,
            "description": description,
            "currency_code": currency_code,
            "payment": payment
        }
        
        if group_id:
            payload["group_id"] = group_id
        
        if date:
            payload["date"] = date
        
        if details:
            payload["details"] = details
            
        if category_id:
            payload["category_id"] = category_id
        
        # Handle user splitting using flattened format
        if users:
            for i, user in enumerate(users):
                if "user_id" in user:
                    payload[f"users__{i}__user_id"] = user["user_id"]
                if "paid_share" in user:
                    payload[f"users__{i}__paid_share"] = user["paid_share"]
                if "owed_share" in user:
                    payload[f"users__{i}__owed_share"] = user["owed_share"]
        
        response = await self.client.post(
            "/create_expense",
            headers=self._get_headers(),
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        
        if response.status_code != 200:
            raise ValueError(f"API request failed: {data.get('errors', 'Unknown error')}")
        
        # Debug: print the response structure
        print(f"API Response: {data}")
        
        if "expense" not in data:
            raise ValueError(f"Unexpected API response structure: {data}")
        
        return SplitwiseExpense(**data["expense"])


def get_splitwise_config() -> SplitwiseConfig:
    """Get Splitwise configuration from environment variables"""
    return SplitwiseConfig(
        consumer_key=os.getenv("SPLITWISE_CONSUMER_KEY"),
        consumer_secret=os.getenv("SPLITWISE_CONSUMER_SECRET"),
        access_token=os.getenv("SPLITWISE_ACCESS_TOKEN"),
        api_key=os.getenv("SPLITWISE_API_KEY")
    )


@mcp.tool()
async def add_expense(
    cost: str,
    description: str,
    group_id: Optional[int] = None,
    users: Optional[List[Dict[str, Any]]] = None,
    currency_code: str = "USD",
    date: Optional[str] = None,
    details: Optional[str] = None,
    payment: bool = False,
    category_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Add a new expense to Splitwise with user splitting support.
    
    Args:
        cost: The total cost of the expense (e.g., "25.50")
        description: Description of the expense
        group_id: Optional group ID to add the expense to
        users: List of users with their shares [{"user_id": int, "paid_share": str, "owed_share": str}]
        currency_code: Currency code (default: USD)
        date: Date of the expense in YYYY-MM-DD format
        details: Additional details about the expense
        payment: Whether this is a payment (settlement) rather than an expense
        category_id: Optional category ID for the expense
    
    Returns:
        Dictionary containing the created expense information
    """
    config = get_splitwise_config()
    
    if not config.api_key:
        raise ValueError("SPLITWISE_API_KEY environment variable is required")
    
    async with SplitwiseClient(config) as client:
        expense = await client.create_expense(
            cost=cost,
            description=description,
            group_id=group_id,
            users=users,
            currency_code=currency_code,
            date=date,
            details=details,
            payment=payment,
            category_id=category_id
        )
        
        return {
            "id": expense.id,
            "description": expense.description,
            "cost": expense.cost,
            "currency_code": expense.currency_code,
            "date": expense.date,
            "group_id": expense.group_id,
            "created_at": expense.created_at,
            "success": True
        }


@mcp.tool()
async def get_users() -> List[Dict[str, Any]]:
    """
    Get all users (friends) from Splitwise.
    
    Returns:
        List of user dictionaries with id, name, and email information
    """
    config = get_splitwise_config()
    
    if not config.api_key:
        raise ValueError("SPLITWISE_API_KEY environment variable is required")
    
    async with SplitwiseClient(config) as client:
        friends = await client.get_friends()
        
        return [
            {
                "id": friend.id,
                "first_name": friend.first_name,
                "last_name": friend.last_name,
                "full_name": f"{friend.first_name} {friend.last_name or ''}".strip(),
                "email": friend.email,
                "registration_status": friend.registration_status
            }
            for friend in friends
        ]


@mcp.tool()
async def get_groups() -> List[Dict[str, Any]]:
    """
    Get all groups from Splitwise.
    
    Returns:
        List of group dictionaries with id, name, and member information
    """
    config = get_splitwise_config()
    
    if not config.api_key:
        raise ValueError("SPLITWISE_API_KEY environment variable is required")
    
    async with SplitwiseClient(config) as client:
        groups = await client.get_groups()
        
        return [
            {
                "id": group.id,
                "name": group.name,
                "created_at": group.created_at,
                "updated_at": group.updated_at,
                "member_count": len(group.members),
                "members": [
                    {
                        "id": member.id,
                        "first_name": member.first_name,
                        "last_name": member.last_name,
                        "full_name": f"{member.first_name} {member.last_name or ''}".strip(),
                        "email": member.email
                    }
                    for member in group.members
                ],
                "simplify_by_default": group.simplify_by_default,
            }
            for group in groups
        ]


@mcp.tool()
async def get_current_user() -> Dict[str, Any]:
    """
    Get current user information from Splitwise.
    
    Returns:
        Dictionary containing current user's profile information
    """
    config = get_splitwise_config()
    
    if not config.api_key:
        raise ValueError("SPLITWISE_API_KEY environment variable is required")
    
    async with SplitwiseClient(config) as client:
        user = await client.get_current_user()
        
        return {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": f"{user.first_name} {user.last_name or ''}".strip(),
            "email": user.email,
            "registration_status": user.registration_status,
            "picture": user.picture
        }


if __name__ == "__main__":
    # Run the MCP server
    mcp.run()