#!/usr/bin/env python3
"""
Remote MCP Server Template - Domain Checker

This is a template for creating remote MCP servers that can be deployed to 
DigitalOcean App Platform. This specific implementation provides domain 
availability checking capabilities.

DEPLOYMENT WORKFLOW:
1. Deploy this server to DigitalOcean using the one-click deploy button
2. Get the deployed URL from DigitalOcean (e.g., https://your-app.ondigitalocean.app)
3. Use that URL + /mcp in your MCP client configuration:
   - Claude Desktop/Code
   - Cursor
   - Windsurf
   - Other MCP-compatible applications

Example MCP client configuration:
{
  "mcpServers": {
    "domain-checker": {
      "url": "https://your-app.ondigitalocean.app/mcp",
      "description": "Check domain availability"
    }
  }
}

This template demonstrates how to build remote MCP servers that can be easily
deployed and consumed by MCP clients without local installation.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List
import whois
import dns.resolver
from fastmcp import FastMCP

# Configure logging for the MCP server
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("domain-checker")

# Create the FastMCP server instance
# This is the main MCP server object that will handle client connections
mcp = FastMCP(
    name="Domain Checker",
    instructions="When you are asked about domain availability or to check if a domain is available for registration, call the appropriate function."
)

class DomainChecker:
    """Domain availability checker with multiple verification methods
    
    This class encapsulates the core domain checking logic that will be
    exposed through MCP tools. It uses both WHOIS and DNS resolution
    to determine if a domain is likely available for registration.
    """
    
    def __init__(self):
        # Configure DNS resolver with reasonable timeouts
        # These settings prevent the MCP server from hanging on slow DNS queries
        self.dns_resolver = dns.resolver.Resolver()
        self.dns_resolver.timeout = 5
        self.dns_resolver.lifetime = 10
    
    async def check_domain_availability(self, domain: str) -> Dict[str, Any]:
        """Check if a domain is available using multiple methods
        
        This is the main async method that coordinates domain checking.
        MCP tools must be async to avoid blocking the server.
        """
        # Initialize result structure with all possible fields
        results = {
            "domain": domain,
            "available": None,
            "whois_available": None,
            "dns_resolvable": None,
            "error": None,
            "details": {}
        }
        
        try:
            # Method 1: WHOIS lookup (checks domain registration records)
            whois_result = await self._check_whois(domain)
            results["whois_available"] = whois_result["available"]
            results["details"]["whois"] = whois_result
            
            # Method 2: DNS resolution check (checks if domain resolves to IP)
            dns_result = await self._check_dns_resolution(domain)
            results["dns_resolvable"] = dns_result["resolvable"]
            results["details"]["dns"] = dns_result
            
            # Determine overall availability using both methods
            # A domain is likely available if WHOIS shows it's free AND it doesn't resolve
            if results["whois_available"] is True and results["dns_resolvable"] is False:
                results["available"] = True
            elif results["whois_available"] is False:
                results["available"] = False
            else:
                results["available"] = None
                
        except Exception as e:
            results["error"] = str(e)
            logger.error(f"Error checking domain {domain}: {e}")
        
        return results
    
    async def _check_whois(self, domain: str) -> Dict[str, Any]:
        """Check domain availability using WHOIS
        
        WHOIS is a synchronous operation, so we use run_in_executor to
        make it async-compatible for the MCP server.
        """
        try:
            loop = asyncio.get_event_loop()
            # Run the blocking WHOIS lookup in a thread pool to keep the MCP server responsive
            whois_data = await loop.run_in_executor(None, whois.whois, domain)
            
            if whois_data is None:
                return {"available": True, "reason": "No WHOIS data found"}
            
            if hasattr(whois_data, 'status') and whois_data.status:
                return {
                    "available": False, 
                    "reason": "Domain has active status",
                    "status": whois_data.status,
                    "registrar": getattr(whois_data, 'registrar', None),
                    "creation_date": str(getattr(whois_data, 'creation_date', None))
                }
            
            if hasattr(whois_data, 'registrar') and whois_data.registrar:
                return {
                    "available": False,
                    "reason": "Domain has registrar",
                    "registrar": whois_data.registrar
                }
            
            return {
                "available": None,
                "reason": "WHOIS data exists but unclear status",
                "raw_data": str(whois_data)[:500]
            }
            
        except whois.parser.PywhoisError as e:
            return {"available": True, "reason": f"WHOIS parser error: {str(e)}"}
        except Exception as e:
            return {"available": None, "reason": f"WHOIS lookup failed: {str(e)}"}
    
    async def _check_dns_resolution(self, domain: str) -> Dict[str, Any]:
        """Check if domain resolves via DNS
        
        DNS resolution is also synchronous, so we wrap it in run_in_executor
        to maintain async compatibility for the MCP server.
        """
        try:
            loop = asyncio.get_event_loop()
            
            def resolve_dns():
                """Helper function to resolve DNS in thread pool"""
                try:
                    answers = self.dns_resolver.resolve(domain, 'A')
                    return [str(answer) for answer in answers]
                except dns.resolver.NXDOMAIN:
                    return None
                except Exception as e:
                    raise e
            
            # Run DNS resolution in thread pool to avoid blocking the MCP server
            a_records = await loop.run_in_executor(None, resolve_dns)
            
            if a_records:
                return {
                    "resolvable": True,
                    "a_records": a_records,
                    "reason": "Domain resolves to IP addresses"
                }
            else:
                return {
                    "resolvable": False,
                    "reason": "Domain does not resolve (NXDOMAIN)"
                }
                
        except Exception as e:
            return {
                "resolvable": None,
                "reason": f"DNS lookup failed: {str(e)}"
            }

# Initialize domain checker instance
# This will be used by all MCP tools
domain_checker = DomainChecker()

# MCP TOOLS
# Tools are functions that MCP clients can call to perform actions
# They must be decorated with @mcp.tool() and should be async

@mcp.tool()
async def check_domain(domain: str) -> str:
    """Check if a single domain name is available for registration
    
    This is an MCP tool that can be called by clients like Claude Desktop.
    It returns a formatted string response for easy reading.
    """
    result = await domain_checker.check_domain_availability(domain)
    
    # Format the response nicely
    if result["available"] is True:
        status = "✅ LIKELY AVAILABLE"
    elif result["available"] is False:
        status = "❌ NOT AVAILABLE"
    else:
        status = "❓ UNCLEAR"
    
    response = f"""Domain: {domain}
Status: {status}

WHOIS Check: {'Available' if result['whois_available'] else 'Registered' if result['whois_available'] is False else 'Unclear'}
DNS Resolution: {'Not resolving' if result['dns_resolvable'] is False else 'Resolving' if result['dns_resolvable'] else 'Error'}

Details:
{json.dumps(result['details'], indent=2)}
"""
    
    if result["error"]:
        response += f"\nError: {result['error']}"
    
    return response

@mcp.tool()
async def check_multiple_domains(domains: List[str]) -> str:
    """Check availability for multiple domain names at once
    
    This MCP tool demonstrates how to handle batch operations efficiently
    using asyncio.gather for concurrent execution.
    """
    if not domains:
        return "Error: Domain list is required"
    
    # Check domains concurrently for better performance
    # This is important for MCP servers to avoid blocking on multiple operations
    tasks = [domain_checker.check_domain_availability(domain) for domain in domains]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle any exceptions in the results
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append({
                "domain": domains[i],
                "available": None,
                "error": str(result)
            })
        else:
            processed_results.append(result)
    
    # Format results as a table
    response = "Domain Availability Check Results:\n\n"
    for result in processed_results:
        if result["available"] is True:
            status = "✅ LIKELY AVAILABLE"
        elif result["available"] is False:
            status = "❌ NOT AVAILABLE"
        else:
            status = "❓ UNCLEAR"
        
        response += f"{result['domain']:<30} {status}\n"
    
    response += f"\nDetailed results:\n{json.dumps(processed_results, indent=2)}"
    
    return response

# MCP RESOURCES
# Resources are data that can be accessed by MCP clients using URIs
# They provide a way to expose structured data through the MCP protocol

@mcp.resource("domain://check/{domain}")
async def domain_info_resource(domain: str) -> str:
    """Get domain availability information as a resource
    
    This MCP resource allows clients to access domain data using a URI like:
    domain://check/example.com
    
    Resources return raw data (JSON) rather than formatted strings.
    """
    result = await domain_checker.check_domain_availability(domain)
    return json.dumps(result, indent=2)

# MCP SERVER STARTUP
# This section configures and starts the MCP server
if __name__ == "__main__":
    # Get port from environment variable (used by deployment platforms like DigitalOcean)
    port = int(os.environ.get("PORT", 8080))
    
    # Start the MCP server with HTTP transport
    # - transport="streamable-http": Uses HTTP for communication with MCP clients
    # - host="0.0.0.0": Accepts connections from any IP (needed for remote deployment)
    # - port: The port to listen on
    # - log_level="debug": Enables detailed logging for development
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port, log_level="debug")