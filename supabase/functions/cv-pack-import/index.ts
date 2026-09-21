import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";
import { unzipSync } from "npm:fflate@0.8.2";

const BUCKET = "founder-cv-portfolio";
const PACK_ID = "2026-09_FINAL";
const PACK_ROOT = "OpportunityOS_CV_Pack/";
const MAX_PACK_BYTES = 2_000_000;

type Asset = {
  filename: string;
  targetPath: string;
  contentType: string;
  productionPdf?: boolean;
};

const ASSETS: Asset[] = [
  { filename: "Mohammed_Ehab_AI_Engineer_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_AI_Engineer_CV_2026.pdf", contentType: "application/pdf", productionPdf: true },
  { filename: "Mohammed_Ehab_Business_Analyst_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_Business_Analyst_CV_2026.pdf", contentType: "application/pdf", productionPdf: true },
  { filename: "Mohammed_Ehab_Data_Analyst_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_Data_Analyst_CV_2026.pdf", contentType: "application/pdf", productionPdf: true },
  { filename: "Mohammed_Ehab_Data_Engineer_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_Data_Engineer_CV_2026.pdf", contentType: "application/pdf", productionPdf: true },
  { filename: "Mohammed_Ehab_Data_Scientist_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_Data_Scientist_CV_2026.pdf", contentType: "application/pdf", productionPdf: true },
  { filename: "Mohammed_Ehab_Master_CV_2026.pdf", targetPath: "2026/Mohammed_Ehab_Master_CV_2026.pdf", contentType: "application/pdf", productionPdf: true },

  { filename: "Mohammed_Ehab_AI_Engineer_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_AI_Engineer_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
  { filename: "Mohammed_Ehab_Business_Analyst_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_Business_Analyst_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
  { filename: "Mohammed_Ehab_Data_Analyst_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_Data_Analyst_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
  { filename: "Mohammed_Ehab_Data_Engineer_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_Data_Engineer_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
  { filename: "Mohammed_Ehab_Data_Scientist_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_Data_Scientist_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
  { filename: "Mohammed_Ehab_Master_CV_2026.docx", targetPath: "2026/editable/Mohammed_Ehab_Master_CV_2026.docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },

  { filename: "ATS_AUDIT.md", targetPath: "2026/system/ATS_AUDIT.md", contentType: "text/markdown" },
  { filename: "OpportunityOS_CV_Registry.json", targetPath: "2026/system/OpportunityOS_CV_Registry.json", contentType: "application/json" },
  { filename: "README_CV_SYSTEM.md", targetPath: "2026/system/README_CV_SYSTEM.md", contentType: "text/markdown" },
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

function findAssetBytes(entries: Record<string, Uint8Array>, filename: string): Uint8Array | null {
  return entries[PACK_ROOT + filename] ?? entries[filename] ?? null;
}

function startsWithAscii(bytes: Uint8Array, text: string): boolean {
  if (bytes.byteLength < text.length) return false;
  for (let i = 0; i < text.length; i += 1) {
    if (bytes[i] !== text.charCodeAt(i)) return false;
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

  // Defense in depth beyond verify_jwt: only the singleton Founder identity may import.
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
    const bytes = findAssetBytes(entries, asset.filename);
    if (!bytes) return json({ detail: `missing required asset: ${asset.filename}` }, 422);
    if (asset.filename.endsWith(".pdf") && !startsWithAscii(bytes, "%PDF-")) {
      return json({ detail: `invalid PDF payload: ${asset.filename}` }, 422);
    }
    if (asset.filename.endsWith(".docx") && !startsWithAscii(bytes, "PK")) {
      return json({ detail: `invalid DOCX payload: ${asset.filename}` }, 422);
    }
    prepared.push({ ...asset, bytes, sha256: await sha256(bytes), size: bytes.byteLength });
  }

  // Validate registry identity and ensure all five role-specific pairs named by the registry exist.
  try {
    const registryBytes = findAssetBytes(entries, "OpportunityOS_CV_Registry.json")!;
    const registry = JSON.parse(new TextDecoder().decode(registryBytes)) as {
      candidate?: unknown;
      base_cvs?: Array<{ pdf?: unknown; docx?: unknown }>;
    };
    if (registry.candidate !== "Mohammed Ehab ElNomany") {
      return json({ detail: "CV registry candidate does not match the Founder pack" }, 422);
    }
    const named = new Set((registry.base_cvs ?? []).flatMap((row) => [String(row.pdf ?? ""), String(row.docx ?? "")]));
    for (const asset of ASSETS.filter((a) => !a.filename.includes("Master") && (a.filename.endsWith(".pdf") || a.filename.endsWith(".docx")))) {
      if (!named.has(asset.filename)) return json({ detail: `registry does not declare required role asset: ${asset.filename}` }, 422);
    }
  } catch {
    return json({ detail: "OpportunityOS_CV_Registry.json is invalid" }, 422);
  }

  const service = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  // The full pack is validated before any production object is replaced.
  const archiveHash = await sha256(archiveBytes);
  const uploaded: Array<{ filename: string; object_path: string; sha256: string; size: number }> = [];

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

  // Keep the exact authoritative source bundle privately alongside its expanded assets.
  const archivePath = `2026/system/OpportunityOS_CV_Pack_${PACK_ID}.zip`;
  const { error: archiveUploadError } = await service.storage
    .from(BUCKET)
    .upload(archivePath, new Blob([archiveBytes], { type: "application/zip" }), {
      upsert: true,
      contentType: "application/zip",
      cacheControl: "0",
    });
  if (archiveUploadError) return json({ detail: "authoritative pack archive upload failed", error: archiveUploadError.message }, 500);

  // Verify every stored object byte-for-byte before changing the website's selection hashes.
  for (const asset of prepared) {
    const { data, error } = await service.storage.from(BUCKET).download(asset.targetPath);
    if (error || !data) return json({ detail: `could not verify stored asset: ${asset.filename}`, error: error?.message }, 500);
    const stored = new Uint8Array(await data.arrayBuffer());
    const storedHash = await sha256(stored);
    if (storedHash !== asset.sha256) return json({ detail: `checksum mismatch after upload: ${asset.filename}` }, 500);
  }

  // Existing website selections already point at these stable PDF paths.
  // Update their checksums only after all new assets have been uploaded and verified.
  for (const asset of prepared.filter((a) => a.productionPdf)) {
    const { error } = await service
      .from("founder_cv_selections")
      .update({ sha256: asset.sha256 })
      .eq("object_path", asset.targetPath);
    if (error) return json({ detail: `could not update selection checksum for ${asset.filename}`, error: error.message }, 500);
  }

  return json({
    status: "imported",
    pack_id: PACK_ID,
    archive: { object_path: archivePath, sha256: archiveHash, size: archiveBytes.byteLength },
    assets: uploaded,
    production_pdfs_replaced: prepared.filter((a) => a.productionPdf).length,
    editable_docx_stored: prepared.filter((a) => a.filename.endsWith(".docx")).length,
    system_files_stored: prepared.filter((a) => a.targetPath.startsWith("2026/system/")).length + 1,
  });
});
