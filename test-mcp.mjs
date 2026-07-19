import { createMCPClient } from "@ai-sdk/mcp";
import { createToolSchemas } from "@supabase/mcp-server-supabase";

const mcpClient = await createMCPClient({
  transport: {
    type: "http",
    url: "https://mcp.supabase.com/mcp"
  }
});

console.log("Connected!");
