ALTER TABLE plans DROP CONSTRAINT plans_kind_check;
ALTER TABLE plans ADD CONSTRAINT plans_kind_check CHECK (kind IN ('SINGLE','COUPLE','GROUP'));
ALTER TABLE plans ADD COLUMN cover_image_url text;

-- New IDs preserve the names and pricing of existing bookings and saved looks.
INSERT INTO plans(id,slug,kimono_id,name,summary,description,audience,duration_minutes,base_price,included_items,is_demo,kind,additional_guest_price,cover_image_url)
SELECT v.id::uuid,v.slug,k.id,jsonb_build_object('zh-Hant',v.name),
 jsonb_build_object('zh-Hant',v.description),jsonb_build_object('zh-Hant',v.description || ' 價格為開發測試假資料；女生腰帶可另行加購。'),
 ARRAY[v.kind],480,v.price,'["和服租借（測試）","著裝服務（測試）"]'::jsonb,true,v.kind,v.guest_price,v.cover
FROM (VALUES
 ('30000000-0000-4000-8000-000000000011','demo-single-experience','單人和服體驗','一位旅客，自由選擇男生或女生和服。','SINGLE',1500,1500,'/assets/plan-single.webp'),
 ('30000000-0000-4000-8000-000000000012','demo-couple-experience','情侶和服體驗','固定一男一女，共兩位旅客，整組計價。','COUPLE',2800,0,'/assets/plan-couple.webp'),
 ('30000000-0000-4000-8000-000000000013','demo-group-experience','團體和服體驗','兩至三位旅客，每人 NT$1,400，各自選擇和服性別與款式。','GROUP',1400,1400,'/assets/plan-group.webp')
) AS v(id,slug,name,description,kind,price,guest_price,cover)
CROSS JOIN LATERAL (SELECT id FROM kimonos WHERE sku='RKH0002' AND is_demo LIMIT 1) k;

INSERT INTO plan_stores(plan_id,store_id)
 SELECT p.id,s.id FROM plans p CROSS JOIN stores s
 WHERE p.slug IN ('demo-single-experience','demo-couple-experience','demo-group-experience') AND s.is_demo AND s.active;
INSERT INTO plan_kimonos(plan_id,kimono_id)
 SELECT p.id,k.id FROM plans p CROSS JOIN kimonos k
 WHERE p.slug IN ('demo-single-experience','demo-couple-experience','demo-group-experience')
 AND k.sku IN ('RKH0002','RKH0057','RKH0103','RKM0001','RKM0002','RKM0003');
UPDATE plans SET active=false WHERE is_demo AND slug IN ('demo-rkh0002','demo-rkh0057','demo-rkh0103','demo-couple');
