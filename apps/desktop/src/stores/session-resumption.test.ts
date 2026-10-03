import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'
import { nativeFailure } from '@/pages/native/native-utils'
import { MockLocalChatGateway } from '@/shared/api/mock-local-chat-gateway'
import { MockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { RealLocalChatGateway } from '@/shared/api/local-chat-gateway'
import { RemoteGateway } from '@/shared/api/remote-gateway'
import { setLocalChatGatewayForTesting } from '@/shared/api/local-chat-provider'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'
import { remoteRequestFailure } from '@/shared/api/remote-diagnostics'
import { useChatStore } from './chat.store'
import { useRemoteChatStore } from './remote-chat.store'

const sceneFallback='无法接着上一轮继续，请点右上角 + 开启新话题'
const nativeFallback='该原生会话暂时无法续接，请稍后重试或在电脑上核对'
const reason='上一轮仍需本机恢复核对，请在电脑端确认后再续接'
beforeEach(()=>{setActivePinia(createPinia());remoteRequestFailure.value=null})
afterEach(()=>{useChatStore().stopPolling();useRemoteChatStore().reset();setLocalChatGatewayForTesting(null);setRemoteGatewayForTesting(null);vi.unstubAllGlobals();vi.restoreAllMocks();remoteRequestFailure.value=null})

describe('resumption reason presentation',()=>{
  it.each(['scenario','native'] as const)('prefers the supplied safe reason for %s',kind=>{
    expect(getRemoteErrorMessage('SESSION_NOT_RESUMABLE',reason,kind)).toBe(reason)
  })
  it('uses kind-specific fallbacks only for missing or blank reasons',()=>{
    for(const message of [undefined,null,'','   ']) {
      expect(getRemoteErrorMessage('SESSION_NOT_RESUMABLE',message,'scenario')).toBe(sceneFallback)
      expect(getRemoteErrorMessage('SESSION_NOT_RESUMABLE',message,'native')).toBe(nativeFallback)
    }
    expect(nativeFailure({code:'SESSION_NOT_RESUMABLE'}).message).toBe(nativeFallback)
    expect(nativeFailure({code:'SESSION_NOT_RESUMABLE',message:reason}).message).toBe(reason)
    expect(getRemoteErrorMessage('REMOTE_DEVICE_OFFLINE','raw')).toBe('设备离线，发送失败')
  })
  describe.each([false,true])('HTTP to rendered store error remote=%s',isRemote=>{
    it.each([
      {kind:'scenario' as const,message:reason,expected:reason},
      {kind:'native' as const,message:reason,expected:reason},
      {kind:'scenario' as const,message:undefined,expected:sceneFallback},
      {kind:'native' as const,message:undefined,expected:nativeFallback},
      {kind:'native' as const,message:'   ',expected:nativeFallback},
    ])('shows $expected for $kind with message=$message',async({kind,message,expected})=>{
      if(isRemote){
        const mock=new MockRemoteGateway();mock.reset();mock.runs=[];mock.commands=[];mock.devices[0].supportedWireRevisions=[4]
        setRemoteGatewayForTesting(mock)
        await useRemoteChatStore().fetchDevices();await useRemoteChatStore().selectDevice('worker_demo')
        useRemoteChatStore().activeConversation!.conversationKind=kind
        setRemoteGatewayForTesting(new RemoteGateway())
      }else{
        setLocalChatGatewayForTesting(new MockLocalChatGateway())
        await useChatStore().init();await useChatStore().selectConversation('conv_analyze_auth')
        useChatStore().activeConversation!.conversationKind=kind
        setLocalChatGatewayForTesting(new RealLocalChatGateway())
      }
      // An HTTP status phrase is not the safe business reason and must not mask missing message.
      vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({success:false,protocolVersion:'0.10.0',error:{code:'SESSION_NOT_RESUMABLE',...(message!==undefined?{message}:{})}}),{status:409,statusText:'Conflict'})))
      if(isRemote){
        await expect(useRemoteChatStore().sendMessage('续接测试')).rejects.toMatchObject({code:'SESSION_NOT_RESUMABLE'})
        expect(useRemoteChatStore().sendError).toBe(expected)
        if(!message?.trim()) expect(remoteRequestFailure.value).toBeNull()
        else expect(remoteRequestFailure.value?.message).toBe(reason)
      }else{
        await expect(useChatStore().sendMessage('续接测试','continue')).rejects.toMatchObject({code:'SESSION_NOT_RESUMABLE'})
        expect(useChatStore().resumptionError).toBe(expected)
      }
    })
  })
})
