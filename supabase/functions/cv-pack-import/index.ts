import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";
import { unzipSync } from "npm:fflate@0.8.2";

const BUCKET = "founder-cv-portfolio";
const PACK_ID = "2026-09-21_FINAL_9CV";
const MAX_PACK_BYTES = 2_000_000;

type Asset = {
  sourcePath: string;
  filename: string;
  targetPath: string;
  contentType: string;
  expectedSha256: string;
  productionPdf?: boolean;
};

const ASSETS: Asset[] = [
  { sourcePath: "CVs/Mohammed_Ehab_Data_Engineering_Integration_CV_2026.pdf", filename: "Mohammed_Ehab_Data_Engineering_Integration_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_Data_Engineering_Integration_CV_2026.pdf", contentType: "application/pdf", expectedSha256: "80fe24c23364efe94525147609e1c70554d2347e06d11632015fd7095789a405", productionPdf: true },
  { sourcePath: "CVs/Mohammed_Ehab_Data_Analytics_BI_CV_2026.pdf", filename: "Mohammed_Ehab_Data_Analytics_BI_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_Data_Analytics_BI_CV_2026.pdf", contentType: "application/pdf", expectedSha256: "56558cb5c618be45b0261ac9730a13f38088d50ff6869dba9a257e00cd8326a9", productionPdf: true },
  { sourcePath: "CVs/Mohammed_Ehab_Data_Scientist_CV_2026.pdf", filename: "Mohammed_Ehab_Data_Scientist_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_Data_Scientist_CV_2026.pdf", contentType: "application/pdf", expectedSha256: "d6d7119d908eb05ce30e0d6b95a2a555c03828ab1be98c94fbd9bcd0158daebd", productionPdf: true },
  { sourcePath: "CVs/Mohammed_Ehab_Machine_Learning_Engineer_CV_2026.pdf", filename: "Mohammed_Ehab_Machine_Learning_Engineer_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_Machine_Learning_Engineer_CV_2026.pdf", contentType: "application/pdf", expectedSha256: "b705a4cc85ad7aca72de8f2832b250e579bdb5e92a5c0f77b87e6971471058e3", productionPdf: true },
  { sourcePath: "CVs/Mohammed_Ehab_AI_LLM_Engineer_CV_2026.pdf", filename: "Mohammed_Ehab_AI_LLM_Engineer_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_AI_LLM_Engineer_CV_2026.pdf", contentType: "application/pdf", expectedSha256: "d4de3d8a5a634000fe4f4fc880fddbdf9f049653486244b1249b86dec4de651d", productionPdf: true },
  { sourcePath: "CVs/Mohammed_Ehab_Business_Technical_Analyst_CV_2026.pdf", filename: "Mohammed_Ehab_Business_Technical_Analyst_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_Business_Technical_Analyst_CV_2026.pdf", contentType: "application/pdf", expectedSha256: "63142654468062da55dfe5821127ce80547915205ca52eb2a413a2bea6e42f3c", productionPdf: true },
  { sourcePath: "CVs/Mohammed_Ehab_AI_Technical_Solutions_Engineer_CV_2026.pdf", filename: "Mohammed_Ehab_AI_Technical_Solutions_Engineer_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_AI_Technical_Solutions_Engineer_CV_2026.pdf", contentType: "application/pdf", expectedSha256: "41a1a54342a9c1db091ffce7c68f2755ee3c51a8ea33abfa153e73b07b1ffd87", productionPdf: true },
  { sourcePath: "CVs/Mohammed_Ehab_Full_Stack_Product_Engineer_CV_2026.pdf", filename: "Mohammed_Ehab_Full_Stack_Product_Engineer_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_Full_Stack_Product_Engineer_CV_2026.pdf", contentType: "application/pdf", expectedSha256: "5b01d3bfb83bc90a67902f668499d42fa33146928bc6a1f05b29c760999ebf60", productionPdf: true },
  { sourcePath: "CVs/Mohammed_Ehab_Master_Comprehensive_CV_2026.pdf", filename: "Mohammed_Ehab_Master_Comprehensive_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_Master_Comprehensive_CV_2026.pdf", contentType: "application/pdf", expectedSha256: "f20ceec79d450f66d241640f36fbcbac74ee2d365da7e29e4d11883c352e5407", productionPdf: true },

  { sourcePath: "CVs/Mohammed_Ehab_Data_Engineering_Integration_CV_2026.docx", filename: "Mohammed_Ehab_Data_Engineering_Integration_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_Data_Engineering_Integration_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", expectedSha256: "bda6f94eb577c31cbd1a5a4162643e7832571314bbedf9c54fde4d7cbeba0bc7" },
  { sourcePath: "CVs/Mohammed_Ehab_Data_Analytics_BI_CV_2026.docx", filename: "Mohammed_Ehab_Data_Analytics_BI_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_Data_Analytics_BI_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", expectedSha256: "5c6206a5dc7a31c2872273d9de85e6a94bde1de9539fe665e728f21fd64154de" },
  { sourcePath: "CVs/Mohammed_Ehab_Data_Scientist_CV_2026.docx", filename: "Mohammed_Ehab_Data_Scientist_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_Data_Scientist_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", expectedSha256: "0e078110df8ef5005eebcc28114db473814bdf287a47a5ef44403c0a56d99417" },
  { sourcePath: "CVs/Mohammed_Ehab_Machine_Learning_Engineer_CV_2026.docx", filename: "Mohammed_Ehab_Machine_Learning_Engineer_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_Machine_Learning_Engineer_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", expectedSha256: "024ced5ae2088d4815385065499ed6cd579a286bd3d19c7464420ad40eb0d870" },
  { sourcePath: "CVs/Mohammed_Ehab_AI_LLM_Engineer_CV_2026.docx", filename: "Mohammed_Ehab_AI_LLM_Engineer_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_AI_LLM_Engineer_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", expectedSha256: "512899411c6365198920c1d381020a4559064622909f8f2333e0442e1aca09ba" },
  { sourcePath: "CVs/Mohammed_Ehab_Business_Technical_Analyst_CV_2026.docx", filename: "Mohammed_Ehab_Business_Technical_Analyst_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_Business_Technical_Analyst_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", expectedSha256: "e73ca7b70e9bee936d8b46e779a0c927796eb0b2fc9624b3656ed521e90f325c" },
  { sourcePath: "CVs/Mohammed_Ehab_AI_Technical_Solutions_Engineer_CV_2026.docx", filename: "Mohammed_Ehab_AI_Technical_Solutions_Engineer_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_AI_Technical_Solutions_Engineer_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", expectedSha256: "30c99eb0afc2031eb54290524802bd8e61fa4b5ef5dd851a016e21bc9d86b31f" },
  { sourcePath: "CVs/Mohammed_Ehab_Full_Stack_Product_Engineer_CV_2026.docx", filename: "Mohammed_Ehab_Full_Stack_Product_Engineer_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_Full_Stack_Product_Engineer_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", expectedSha256: "bdcaa105260383706097bc77651f88d034589b3a82ee675984c3c075eaa01f27" },
  { sourcePath: "CVs/Mohammed_Ehab_Master_Comprehensive_CV_2026.docx", filename: "Mohammed_Ehab_Master_Comprehensive_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_Master_Comprehensive_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", expectedSha256: "ef1d1ad7acf6c5489cec97821eb506f338a84f2fb1cbecc4b82183223594d1a8" },

  { sourcePath: "Supporting_Documents/MOHAMMED_EHAB_MASTER_PERSONALIZATION.md", filename: "MOHAMMED_EHAB_MASTER_PERSONALIZATION.md", targetPath: "2026/system/MOHAMMED_EHAB_MASTER_PERSONALIZATION.md", contentType: "text/markdown", expectedSha256: "6e1005ec9fc6f0562b870769f431df1cab7ff850ae8f507e4a7521d6e21afcdd" },
  { sourcePath: "Supporting_Documents/MASTER_SKILLS_AND_TECH_STACK.md", filename: "MASTER_SKILLS_AND_TECH_STACK.md", targetPath: "2026/system/MASTER_SKILLS_AND_TECH_STACK.md", contentType: "text/markdown", expectedSha256: "5f2db58cf9c48b7802955d04916f73cac56518893fe0c5d60812517c0bb8be0c" },
  { sourcePath: "Supporting_Documents/PROJECT_TECH_STACK_EVIDENCE.md", filename: "PROJECT_TECH_STACK_EVIDENCE.md", targetPath: "2026/system/PROJECT_TECH_STACK_EVIDENCE.md", contentType: "text/markdown", expectedSha256: "85cdeed30cb70d2c29ab7e8eba3c8184a7849cd183d27025cf68ed4cbbbbe5d6" },
  { sourcePath: "Supporting_Documents/ROLE_CV_MAPPING.md", filename: "ROLE_CV_MAPPING.md", targetPath: "2026/system/ROLE_CV_MAPPING.md", contentType: "text/markdown", expectedSha256: "8f6dea7eff52806cabc1159ac29bc9ed1872e2d85da465c4c19cc71d6a265b83" },
  { sourcePath: "Supporting_Documents/EXPERIENCE_EVIDENCE_MATRIX.md", filename: "EXPERIENCE_EVIDENCE_MATRIX.md", targetPath: "2026/system/EXPERIENCE_EVIDENCE_MATRIX.md", contentType: "text/markdown", expectedSha256: "2e3a7aa7e3732c0705620772e34a4608073af5fd83901bee7e3449a9fa323f9f" },
  { sourcePath: "Supporting_Documents/EDUCATION_CERTIFICATION_SKILLS_MAP.md", filename: "EDUCATION_CERTIFICATION_SKILLS_MAP.md", targetPath: "2026/system/EDUCATION_CERTIFICATION_SKILLS_MAP.md", contentType: "text/markdown", expectedSha256: "21485d76575233339a2316f752c0f3bc5bcb72a7c62b1e8f9d1dae3c46df379f" },
  { sourcePath: "Supporting_Documents/CV_CONTENT_RULES.md", filename: "CV_CONTENT_RULES.md", targetPath: "2026/system/CV_CONTENT_RULES.md", contentType: "text/markdown", expectedSha256: "f17ae00b38b29bd05c089a04fbda8fb7d78bb00982068e77ce9ba8c7812c6368" },
  { sourcePath: "Supporting_Documents/OpportunityOS_CV_Registry.json", filename: "OpportunityOS_CV_Registry.json", targetPath: "2026/system/OpportunityOS_CV_Registry.json", contentType: "application/json", expectedSha256: "201ee75c2675f707b2a24af728f85ed62ceeb25df6667b5ec549a6a50eff4b71" },
  { sourcePath: "Supporting_Documents/truth_pack.yaml", filename: "truth_pack.yaml", targetPath: "2026/system/truth_pack.yaml", contentType: "application/yaml", expectedSha256: "e3b0d1c23888bc5340bcc7409f035971d842ceabaca9f4dc639430f49c5923d0" },
  { sourcePath: "Supporting_Documents/ATS_AUDIT.md", filename: "ATS_AUDIT.md", targetPath: "2026/system/ATS_AUDIT.md", contentType: "text/markdown", expectedSha256: "92da65cf861282fa57d132583d269f1287b643b9020e9192baa2323cacd051e5" },
  { sourcePath: "Supporting_Documents/README_CV_SYSTEM.md", filename: "README_CV_SYSTEM.md", targetPath: "2026/system/README_CV_SYSTEM.md", contentType: "text/markdown", expectedSha256: "140e811a9e84cfce616ab997e2308194718d72bf23a40c416361e2c768f1aedd" },
  { sourcePath: "MANIFEST.md", filename: "MANIFEST.md", targetPath: "2026/system/MANIFEST.md", contentType: "text/markdown", expectedSha256: "4719430bc24ce6a06e8cdc7f9e15fddc8d312a4367653f90631595e3d05155eb" },
];

const LEGACY_SELECTION_MIGRATIONS = [
  { oldPath: "2026/Mohammed_Ehab_AI_Engineer_CV_2026.pdf", variant: "ai_engineer", newPath: "2026/Mohammed_Ehab_AI_LLM_Engineer_CV_2026.pdf", sha256: "d4de3d8a5a634000fe4f4fc880fddbdf9f049653486244b1249b86dec4de651d" },
  { oldPath: "2026/Mohammed_Ehab_Business_Analyst_CV_2026.pdf", variant: "business_analyst", newPath: "2026/Mohammed_Ehab_Business_Technical_Analyst_CV_2026.pdf", sha256: "63142654468062da55dfe5821127ce80547915205ca52eb2a413a2bea6e42f3c" },
  { oldPath: "2026/Mohammed_Ehab_Data_Analyst_CV_2026.pdf", variant: "data_analyst", newPath: "2026/Mohammed_Ehab_Data_Analytics_BI_CV_2026.pdf", sha256: "56558cb5c618be45b0261ac9730a13f38088d50ff6869dba9a257e00cd8326a9" },
  { oldPath: "2026/Mohammed_Ehab_Data_Engineer_CV_2026.pdf", variant: "data_engineer", newPath: "2026/Mohammed_Ehab_Data_Engineering_Integration_CV_2026.pdf", sha256: "80fe24c23364efe94525147609e1c70554d2347e06d11632015fd7095789a405" },
  { oldPath: "2026/Mohammed_Ehab_Data_Scientist_CV_2026.pdf", variant: "data_scientist", newPath: "2026/Mohammed_Ehab_Data_Scientist_CV_2026.pdf", sha256: "d6d7119d908eb05ce30e0d6b95a2a555c03828ab1be98c94fbd9bcd0158daebd" },
  { oldPath: "2026/Mohammed_Ehab_Master_CV_2026.pdf", variant: "master", newPath: "2026/Mohammed_Ehab_Master_Comprehensive_CV_2026.pdf", sha256: "f20ceec79d450f66d241640f36fbcbac74ee2d365da7e29e4d11883c352e5407" },
];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

async function sha256(bytes: Uint8Array): Promise<string> {
  const input = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  return bytesToHex(new Uint8Array(await crypto.subtle.digest("SHA-256", input)));
}

function startsWithAscii(bytes: Uint8Array, value: string): boolean {
  if (bytes.byteLength < value.length) return false;
  for (let i = 0; i < value.length; i += 1) {
    if (bytes[i] !== value.charCodeAt(i)) return false;
  }
  return true;
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ detail: "POST required" }, 405);

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !anonKey || !serviceRoleKey) {
    return json({ detail: "Supabase runtime configuration unavailable" }, 500);
  }

  const authHeader = req.headers.get("authorization");
  if (!authHeader?.startsWith("Bearer ")) return json({ detail: "authentication required" }, 401);

  const founderClient = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authHeader } },
    auth: { persistSession: false },
  });
  const { data: isFounder, error: founderError } = await founderClient.rpc("opos_is_founder");
  if (founderError || isFounder !== true) return json({ detail: "authorized founder required" }, 403);

  const archiveBytes = new Uint8Array(await req.arrayBuffer());
  if (archiveBytes.byteLength === 0 || archiveBytes.byteLength > MAX_PACK_BYTES) {
    return json({ detail: "CV pack must be a non-empty ZIP smaller than 2 MB" }, 422);
  }
  if (!startsWithAscii(archiveBytes, "PK")) return json({ detail: "uploaded file is not a ZIP archive" }, 422);

  let entries: Record<string, Uint8Array>;
  try {
    entries = unzipSync(archiveBytes);
  } catch {
    return json({ detail: "could not read CV pack ZIP" }, 422);
  }

  const prepared: Array<Asset & { bytes: Uint8Array; sha256: string; size: number }> = [];
  for (const asset of ASSETS) {
    const bytes = entries[asset.sourcePath];
    if (!bytes) return json({ detail: `missing required asset: ${asset.sourcePath}` }, 422);
    if (asset.filename.endsWith(".pdf") && !startsWithAscii(bytes, "%PDF-")) {
      return json({ detail: `invalid PDF payload: ${asset.filename}` }, 422);
    }
    if (asset.filename.endsWith(".docx") && !startsWithAscii(bytes, "PK")) {
      return json({ detail: `invalid DOCX payload: ${asset.filename}` }, 422);
    }
    const digest = await sha256(bytes);
    if (digest !== asset.expectedSha256) {
      return json({ detail: `asset checksum does not match the Founder-locked final: ${asset.filename}` }, 422);
    }
    prepared.push({ ...asset, bytes, sha256: digest, size: bytes.byteLength });
  }

  try {
    const registryBytes = entries["Supporting_Documents/OpportunityOS_CV_Registry.json"];
    const registry = JSON.parse(new TextDecoder().decode(registryBytes)) as {
      schema_version?: unknown;
      candidate?: unknown;
      base_cvs?: Array<{ pdf?: unknown; docx?: unknown }>;
      master_cv?: { pdf?: unknown; docx?: unknown };
    };
    if (registry.schema_version !== "2.0") return json({ detail: "CV registry schema_version must be 2.0" }, 422);
    if (registry.candidate !== "Mohammed Ehab ElNomany") {
      return json({ detail: "CV registry candidate does not match the Founder pack" }, 422);
    }
    if ((registry.base_cvs ?? []).length !== 8) {
      return json({ detail: "CV registry must declare exactly eight targeted role families" }, 422);
    }
    const named = new Set((registry.base_cvs ?? []).flatMap((row) => [String(row.pdf ?? ""), String(row.docx ?? "")]));
    named.add(String(registry.master_cv?.pdf ?? ""));
    named.add(String(registry.master_cv?.docx ?? ""));
    for (const asset of ASSETS.filter((a) => a.sourcePath.startsWith("CVs/"))) {
      if (!named.has(asset.filename)) return json({ detail: `registry does not declare required CV asset: ${asset.filename}` }, 422);
    }
  } catch {
    return json({ detail: "OpportunityOS_CV_Registry.json is invalid" }, 422);
  }

  const service = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const archiveHash = await sha256(archiveBytes);
  const uploaded: Array<{ filename: string; object_path: string; sha256: string; size: number }> = [];

  // The entire pack is validated before any production object is replaced.
  for (const asset of prepared) {
    const { error } = await service.storage
      .from(BUCKET)
      .upload(asset.targetPath, new Blob([asset.bytes], { type: asset.contentType }), {
        upsert: true,
        contentType: asset.contentType,
        cacheControl: "0",
      });
    if (error) return json({ detail: `storage upload failed for ${asset.filename}`, error: error.message }, 500);
    uploaded.push({ filename: asset.filename, object_path: asset.targetPath, sha256: asset.sha256, size: asset.size });
  }

  const archivePath = "2026/system/Mohammed_Ehab_CV_System_2026-09-21_FINAL.zip";
  const { error: archiveUploadError } = await service.storage
    .from(BUCKET)
    .upload(archivePath, new Blob([archiveBytes], { type: "application/zip" }), {
      upsert: true,
      contentType: "application/zip",
      cacheControl: "0",
    });
  if (archiveUploadError) return json({ detail: "authoritative pack archive upload failed", error: archiveUploadError.message }, 500);

  for (const asset of prepared) {
    const { data, error } = await service.storage.from(BUCKET).download(asset.targetPath);
    if (error || !data) return json({ detail: `could not verify stored asset: ${asset.filename}`, error: error?.message }, 500);
    const stored = new Uint8Array(await data.arrayBuffer());
    const storedHash = await sha256(stored);
    if (storedHash !== asset.sha256) return json({ detail: `checksum mismatch after upload: ${asset.filename}` }, 500);
  }

  // Migrate durable metadata for the six legacy families whose stable filenames
  // changed. The serving route recomputes selection from the current Python
  // selector, so this only prevents obviously stale metadata from pointing at
  // superseded objects. New ML / Solutions / Full-Stack selections are written
  // naturally on subsequent current-selector evaluations.
  let selectionRowsMigrated = 0;
  for (const migration of LEGACY_SELECTION_MIGRATIONS) {
    const { data, error } = await service
      .from("founder_cv_selections")
      .update({
        variant: migration.variant,
        object_path: migration.newPath,
        sha256: migration.sha256,
      })
      .eq("object_path", migration.oldPath)
      .select("opportunity_id");
    if (error) return json({ detail: `could not migrate selection metadata from ${migration.oldPath}`, error: error.message }, 500);
    selectionRowsMigrated += data?.length ?? 0;
  }

  return json({
    status: "imported",
    pack_id: PACK_ID,
    archive: { object_path: archivePath, sha256: archiveHash, size: archiveBytes.byteLength },
    assets: uploaded,
    production_pdfs_replaced: prepared.filter((a) => a.productionPdf).length,
    editable_docx_stored: prepared.filter((a) => a.filename.endsWith(".docx")).length,
    system_files_stored: prepared.filter((a) => a.targetPath.startsWith("2026/system/")).length + 1,
    selection_rows_migrated: selectionRowsMigrated,
  });
});
