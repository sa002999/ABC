export type MemberProfile={id:string;displayName:string|null;email:string;emailVerified:boolean;phoneNumber:string|null;phoneVerified:boolean}

export function normalizeMobile(country:string, input:string){
 const value=input.replace(/[\s()-]/g,'')
 const phone=value.startsWith('+')?value:country+value.replace(/^0/,'')
 if(!['+886','+81'].includes(country)||!phone.startsWith(country)||! /^(?:\+8869\d{8}|\+81[789]0\d{8})$/.test(phone))
  throw new Error('請輸入有效的台灣或日本手機號碼，並確認所選國碼。')
 return phone
}

export function phoneError(error:unknown){
 const code=(error as {code?:string}|null)?.code
 const messages:Record<string,string>={
  'auth/invalid-phone-number':'Firebase 無法接受這個手機號碼，請確認國碼和號碼。',
  'auth/network-request-failed':'目前無法連線到 Firebase，請檢查網路後重試。',
  'auth/invalid-verification-code':'驗證碼不正確，請重新輸入。',
  'auth/code-expired':'驗證碼已到期，請重新發送。',
  'auth/too-many-requests':'嘗試次數過多，請稍後再試。',
  'auth/quota-exceeded':'簡訊服務目前額度不足，請稍後再試。',
  'auth/invalid-credential':'密碼不正確或驗證已失效，請重新確認。',
  'auth/wrong-password':'密碼不正確，請重新輸入。',
  'auth/captcha-check-failed':'人機驗證未完成，請重試。',
  'auth/unauthorized-domain':'目前網域未獲手機驗證授權，請從正式網站操作。',
  'auth/operation-not-allowed':'此號碼所屬地區或手機驗證尚未啟用，請聯絡客服。',
  'auth/invalid-app-credential':'無法完成人機驗證，請重新操作；本機請使用 Firebase 測試號碼。',
 }
 if(code&&/^auth\/[a-z-]+$/.test(code)){
  return messages[code]??`手機驗證暫時無法完成（${code}），請稍後重試。`
 }
 return error instanceof Error?error.message:'手機驗證暫時無法完成，請稍後重試。'
}
