export type MemberProfile={id:string;displayName:string|null;email:string;emailVerified:boolean;phoneNumber:string|null;phoneVerified:boolean}

export function normalizeMobile(country:string, input:string){
 const value=input.replace(/[\s()-]/g,'')
 const phone=value.startsWith('+')?value:country+value.replace(/^0/,'')
 if(!['+886','+81'].includes(country)||!phone.startsWith(country)||! /^(?:\+8869\d{8}|\+81[789]0\d{8})$/.test(phone))
  throw new Error('請輸入有效的台灣或日本手機號碼，並確認所選國碼。')
 return phone
}
