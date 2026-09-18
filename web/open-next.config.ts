import { defineCloudflareConfig } from "@opennextjs/cloudflare";

export default defineCloudflareConfig({
	// No paid R2 incremental cache; standard static assets and memory cache only.
});
