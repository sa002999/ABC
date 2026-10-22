"""Shared adult outfit validation and authoritative integer TWD package pricing."""
from fastapi import HTTPException


def invalid(code,message):
    raise HTTPException(422,{'code':code,'message':message})


def selected_belts(connection,gender,ids):
    if not ids: return []
    if gender!='FEMALE' or len(ids)!=1:
        invalid('INVALID_ACCESSORY','僅女生可選一條收費腰帶。')
    rows=connection.execute("SELECT id,name,price FROM accessories WHERE id=ANY(%s) AND active AND category='BELT' FOR SHARE",(ids,)).fetchall()
    if len(rows)!=len(ids): invalid('INVALID_ACCESSORY','腰帶已下架或不存在。')
    return rows


def validate_packages(guests,plans):
    for plan_id in {p['id'] for p in plans if p and p.get('kind')=='COUPLE'}:
        group=[g for g,p in zip(guests,plans) if p and p['id']==plan_id]
        if len(group)<2 or sorted(g.guest_type for g in group[:2])!=['ADULT_FEMALE','ADULT_MALE']:
            invalid('INVALID_COUPLE','情侶套餐需一位女生與一位男生；第三人依單人加價計算。')


def pricing_lines(guests,plans):
    validate_packages(guests,plans)
    counts={};lines=[]
    for i,(guest,p) in enumerate(zip(guests,plans)):
        count=counts.get(p['id'],0);counts[p['id']]=count+1
        amount=p['base_price']
        if p.get('kind')=='COUPLE':
            amount=p['base_price'] if count==0 else 0 if count==1 else p['additional_guest_price']
        lines.append({'guestIndex':i,'planId':str(p['id']),'kimonoId':str(guest.kimono_id),
            'name':p['name'],'label':('情侶套餐（兩人）' if count==0 else '套餐第二位（已含）' if count==1 else '第三位單人') if p.get('kind')=='COUPLE' else '單人方案',
            'unitPrice':amount,'quantity':1,'total':amount,'amount':amount})
        for belt in p.get('belts',[]):
            lines.append({'guestIndex':i,'accessoryId':str(belt['id']),'name':belt['name'],'label':belt['name'],
                'unitPrice':belt['price'],'quantity':1,'total':belt['price'],'amount':belt['price']})
    return lines
