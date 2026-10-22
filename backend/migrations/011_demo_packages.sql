-- Explicit development fixtures; no production rows are overwritten.
UPDATE kimonos SET gender='MALE' WHERE is_demo AND sku='RKH0103';
UPDATE plans SET included_items='["和服租借（測試）","著裝服務（測試）"]'::jsonb,
 additional_guest_price=1500 WHERE is_demo;
INSERT INTO plan_stores(plan_id,store_id)
 SELECT p.id,s.id FROM plans p CROSS JOIN stores s
 WHERE p.is_demo AND s.is_demo AND s.active ON CONFLICT DO NOTHING;
INSERT INTO inventory_items(id,code,store_id,kimono_id,is_demo)
 SELECT md5('react-item:'||s.id::text||k.id::text||n::text)::uuid,
 'REACT-'||s.slug||'-'||k.sku||'-'||n,s.id,k.id,true
 FROM stores s CROSS JOIN kimonos k CROSS JOIN generate_series(1,3) n
 WHERE s.is_demo AND s.active AND k.is_demo AND k.active
 AND NOT EXISTS(SELECT 1 FROM inventory_items i WHERE i.store_id=s.id AND i.kimono_id=k.id)
 ON CONFLICT DO NOTHING;
INSERT INTO plans(id,slug,kimono_id,name,summary,description,audience,duration_minutes,base_price,included_items,is_demo,kind,additional_guest_price)
 SELECT '30000000-0000-4000-8000-000000000001','demo-couple',id,
 '{"zh-Hant":"情侶雙人和服體驗"}'::jsonb,'{"zh-Hant":"一女一男，套餐計價一次"}'::jsonb,
 '{"zh-Hant":"開發示範套餐：兩名成人、兩件和服；第三位另計單人價，女生腰帶另外收費。"}'::jsonb,
 ARRAY['COUPLE'],480,2800,'["兩件和服租借（測試）","兩人著裝服務（測試）"]'::jsonb,true,'COUPLE',1500
 FROM kimonos WHERE is_demo AND gender='FEMALE' ORDER BY sku LIMIT 1;
INSERT INTO plan_stores(plan_id,store_id)
 SELECT '30000000-0000-4000-8000-000000000001',id FROM stores WHERE is_demo AND active;
