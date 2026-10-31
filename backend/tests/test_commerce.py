import unittest
from types import SimpleNamespace
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError
from app.modules.bookings.schemas import Guest
from app.modules.catalog.rules import pricing_lines, selected_belts


class CommerceTests(unittest.TestCase):
    def test_couple_fixed_two_and_group_per_person(self):
        plan_id=uuid4();kimono_id=uuid4();belt_id=uuid4()
        guests=[SimpleNamespace(guest_type='ADULT_FEMALE',kimono_id=kimono_id),SimpleNamespace(guest_type='ADULT_MALE',kimono_id=kimono_id),SimpleNamespace(guest_type='ADULT_FEMALE',kimono_id=kimono_id)]
        plan={'id':plan_id,'name':{'zh-Hant':'情侶'},'kind':'COUPLE','base_price':2800,'additional_guest_price':1500}
        plans=[{**plan,'belts':[{'id':belt_id,'name':'腰帶','price':200}]},plan,plan]
        lines=pricing_lines(guests[:2],plans[:2])
        self.assertEqual(sum(l['total'] for l in lines),3000)
        self.assertEqual([l['total'] for l in lines if 'planId' in l],[2800,0])
        with self.assertRaises(HTTPException): pricing_lines(guests,plans)
        with self.assertRaises(HTTPException): pricing_lines(guests[:1],plans[:1])
        with self.assertRaises(HTTPException): pricing_lines([guests[0],guests[0]],plans[:2])
        group={**plan,'kind':'GROUP','base_price':1400}
        for count in (2,3):
            self.assertEqual(sum(l['total'] for l in pricing_lines(guests[:count],[group]*count)),1400*count)
        with self.assertRaises(HTTPException): pricing_lines(guests[:1],[group])
        with self.assertRaises(HTTPException): pricing_lines(guests+[guests[0]],[group]*4)
        single={**plan,'kind':'SINGLE'}
        with self.assertRaises(HTTPException): pricing_lines(guests[:2],[single]*2)

    def test_no_child_no_male_belt_and_no_unknown_belt(self):
        with self.assertRaises(ValidationError): Guest(guestType='CHILD')
        with self.assertRaises(HTTPException): Guest(guestType='ADULT_MALE',accessoryIds=[uuid4()])
        with self.assertRaises(HTTPException): selected_belts(None,'MALE',[uuid4()])
        class Empty:
            def execute(self,*args): return self
            def fetchall(self): return []
        with self.assertRaises(HTTPException): selected_belts(Empty(),'FEMALE',[uuid4()])
