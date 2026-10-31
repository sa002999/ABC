import { z } from 'zod';
import { CatalogError, text } from './catalog.mjs';
import { origin } from './config.mjs';

const uuid = z.string().uuid();
export const tryOnOutfit = z.object({ planId: uuid, kimonoId: uuid, conversationId: uuid.optional() }).strict();
export const prepareTryOn = tryOnOutfit.extend({ source: z.enum(['MODEL','SELF']), modelId: uuid.optional(), photoId: uuid.optional() }).strict();
export const confirmTryOn = z.object({ reviewId: uuid, confirmed: z.literal(true) }).strict();
export const getTryOnJob = z.object({ jobId: uuid }).strict();
export const getTryOnJobs = z.object({ conversationId: uuid.optional() }).strict();
export const createPhotoUpload = tryOnOutfit.extend({ consentAccepted: z.literal(true), consentVersion: z.string().min(1).max(100), contentType: z.enum(['image/jpeg','image/png','image/heic','image/heif']), size: z.number().int().positive().max(10*1024*1024) });
export const completePhotoUpload = z.object({ sessionId: uuid, photoId: uuid }).strict();
const photo = z.object({ photoId: uuid, status: z.enum(['PENDING','FILE_READY','READY','REJECTED','DELETED','EXPIRED']), issues: z.array(z.object({ code:z.string(),message:z.string() })), width:z.number().nullable(), height:z.number().nullable(), qualityStatus:z.string(), previewUrl:z.string().nullable(), previewExpiresIn:z.number().nullable() });
const name = z.union([z.string(), z.record(z.string(), z.string())]);
const job = z.object({ jobId: uuid, source: z.literal('MCP'), status: z.enum(['QUEUED','VALIDATING','GENERATING','SUCCEEDED','FAILED','EXPIRED','DELETED']),
  planId: uuid, kimonoId: uuid, photoId: uuid.nullable(), modelId: uuid.nullable(),
  expiresAt: z.string().nullable(), imageUrl: z.string().nullable(), imageUrlExpiresIn: z.number().nullable(),
  failure: z.object({ code: z.string(), message: z.string() }).nullable(), createdAt: z.string() }).passthrough();

export async function tryOnMediaOrigins(config) {
  try {
    const response = await fetch(new URL('/api/mcp/try-on/media-config', config.apiOrigin), { redirect: 'error', signal: AbortSignal.timeout(2500) });
    if (!response.ok) return [];
    const value = z.object({ imageOrigins: z.array(z.string()).max(4) }).parse(await response.json());
    return value.imageOrigins.map(value => origin(value, 'Private image origin'));
  } catch { return []; }
}

export function createTryOn(config) {
  async function request(path, schema, body, timeout=30000) {
    if (!config.memberAuthorization) throw new CatalogError('MCP_TOKEN_REQUIRED','請在 MCP 連線設定填入本人 Bearer token，勿貼入對話。');
    let response;
    try {
      response = await fetch(new URL('/api/mcp/try-on/' + path, config.apiOrigin), { redirect: 'error', signal: AbortSignal.timeout(timeout),
        method: body ? 'POST' : 'GET', headers: { Accept: 'application/json', Authorization: config.memberAuthorization, ...(body ? { 'Content-Type':'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined });
    } catch { throw new CatalogError('TRY_ON_UNREACHABLE',path.startsWith('photo-')?'照片服務暫時無法連線；請保留目前介面，重試本次上傳或驗證。這項操作不會生成或扣額度。':'試穿服務暫時無法連線；確認送出後若逾時，請以相同 reviewId 重試確認或查詢任務，不要另建生成。'); }
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new CatalogError(data?.error?.code || 'TRY_ON_UNAVAILABLE', data?.error?.message || '試穿服務暫時無法使用，請稍後重試。');
    try { return schema.parse(data); }
    catch { throw new CatalogError('INVALID_TRY_ON_RESPONSE','試穿回應格式不完整，請重新查詢。'); }
  }
  async function adapt(data) {
    const allowed = [...config.imageOrigins, ...await tryOnMediaOrigins(config)];
    const media = {};
    const safe = raw => {
      if (!raw) return null;
      try { const url = new URL(raw, config.apiOrigin); return !url.username && !url.password && allowed.includes(url.origin) ? url.href : null; }
      catch { return null; }
    };
    const adaptJob = value => {
      const { imageUrl, ...rest } = value;
      if (rest.kimonoName) rest.kimonoName = text(rest.kimonoName);
      media[value.jobId] = safe(imageUrl);
      return rest;
    };
    if (data.view === 'tryOnSources') {
      data.planName = text(data.planName); data.kimonoName = text(data.kimonoName);
      data.models = data.models.map(({ previewUrl, ...m }) => { media[m.id] = safe(previewUrl); return { ...m, name: text(m.name) }; });
      data.photos = data.photos.map(({ previewUrl, ...p }) => { media[p.photoId] = safe(previewUrl); return p; });
      data.jobs = data.jobs.map(adaptJob);
      if (data.activeJob) data.activeJob = adaptJob(data.activeJob);
    } else if (data.view === 'tryOnJob') data = { ...adaptJob(data), view: data.view };
    else if (data.view === 'tryOnJobs') data.jobs = data.jobs.map(adaptJob);
    else { data.planName = text(data.planName); data.kimonoName = text(data.kimonoName); if (data.modelName) data.modelName = text(data.modelName); }
    return { ...data, _media: media };
  }
  return {
    async photoConsent() { return request('photo-consent',z.object({view:z.literal('photoConsent'),version:z.string().min(1),text:z.string().min(1),maxBytes:z.number().int().positive(),maxPhotos:z.number().int().positive(),minLongEdge:z.number().int(),maxLongEdge:z.number().int(),formats:z.array(z.string())})); },
    async createPhotoUpload(input) {
      const value=createPhotoUpload.parse(input);
      const data=await request('photo-uploads',z.object({view:z.literal('photoUpload'),sessionId:uuid,photoId:uuid,expiresAt:z.string(),upload:z.object({method:z.literal('POST'),uploadUrl:z.string(),fields:z.record(z.string(),z.string()),expiresAt:z.string(),photoId:uuid})}),value);
      const url=new URL(data.upload.uploadUrl);
      const allowed=await tryOnMediaOrigins(config);
      if (url.protocol!=='https:' || url.username || url.password || url.search || url.hash || !allowed.includes(url.origin) ||
          !data.upload.fields.key?.startsWith('private/try-on/uploads/') || data.upload.fields['Content-Type']!==value.contentType || !data.upload.fields.policy) {
        throw new CatalogError('INVALID_UPLOAD_DESTINATION','照片上傳入口未正確設定，請改用官網新增照片。');
      }
      const {upload,...summary}=data;
      return {...summary,_upload:{url:url.href,fields:upload.fields}};
    },
    async completePhotoUpload(input) {
      const data=await request('photo-uploads/complete',z.object({view:z.literal('photoUploaded'),photo}),completePhotoUpload.parse(input),60000);
      const {previewUrl,...value}=data.photo;
      return {view:data.view,photo:value};
    },
    async sources(input) {
      const outfit = tryOnOutfit.parse(input);
      const uploadUrl = new URL('/try-on', config.webOrigin);
      uploadUrl.searchParams.set('plan', outfit.planId);
      const data = await request('sources', z.object({ view: z.literal('tryOnSources'), planName: name, kimonoName: name,
      models: z.array(z.object({ id: uuid, name, role: z.string(), previewUrl: z.string() }).passthrough()),
      photos: z.array(z.object({ photoId: uuid, previewUrl: z.string().nullable() }).passthrough()), jobs: z.array(job), activeJob: job.nullable() }).passthrough(), outfit);
      return adapt({ ...data, uploadPageUrl: uploadUrl.href });
    },
    async prepare(input) { return adapt(await request('prepare', z.object({ view: z.literal('tryOnReview'), reviewId: uuid, reviewExpiresAt: z.string(), planName: name, kimonoName: name }).passthrough(), prepareTryOn.parse(input))); },
    async confirm(input) { return adapt(await request('confirm', job.extend({ view: z.literal('tryOnJob') }), confirmTryOn.parse(input))); },
    async job(input) { return adapt(await request('jobs/' + getTryOnJob.parse(input).jobId, job.extend({ view: z.literal('tryOnJob') }))); },
    async jobs(input) { const { conversationId } = getTryOnJobs.parse(input); return adapt(await request('jobs' + (conversationId ? '?conversation_id=' + conversationId : ''), z.object({ view: z.literal('tryOnJobs'), jobs: z.array(job), notice: z.string() }))); },
  };
}
