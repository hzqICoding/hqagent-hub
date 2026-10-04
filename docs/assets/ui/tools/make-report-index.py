from pathlib import Path
import json
from audit_paths import OUT as p
m=json.loads((p/'manifest.json').read_text(encoding='utf-8'))
mobile='登录|登录错误|登录提交中|设备列表|设备菜单|设备删除确认|选择面板|设备空态|设备加载|设备错误|配对输入|配对预览|配对错误|扫码预览|扫码权限拒绝|对话待机|新话题标签|退出确认|对话列表|新建任务|项目选择|当前对话无消息|对话加载|运行中|运行详情|忙碌|运行失败|审批卡片|电脑离线|远程暂停|请求错误|消息附件各状态|附件上传|附件上传失败|原生对话|原生列表折叠|暂不支持分组|不可用说明|令牌空态|令牌列表|令牌创建|令牌一次性展示|令牌吊销确认|对话设置|仅电脑可见确认|无对话点击发送'.split('|')
desktop='本地运行中|本地待机|删除对话确认|原生面板|Agent 管理|图片能力状态|模型用量确认|场景列表|PI 角色配置|连接手机未配对|授权根目录|配对二维码|工作区|工作区表单|设置占位|概览|团队|任务|会话|审批|模板|更新占位|本机连接|引导|任务详情|本地对话空态|本地对话错误|删除冲突|审批确认|工作区缺少记忆目录|组件样例（仅开发）'.split('|')
lines=['# 截图覆盖索引','','全部为 mock；原尺寸 PNG，截图不含真实用户数据。每个状态都有亮暗主题。完整浏览入口：[画廊](gallery.html)。','']
for prefix,names in [('M',mobile),('D',desktop)]:
 profiles=['mobile-375-light','mobile-375-dark','mobile-390-light','mobile-390-dark'] if prefix=='M' else ['desktop-light','desktop-dark']
 lines += [('## 手机 375×812 / 390×844' if prefix=='M' else '## 电脑 1280×800'),'','| 状态 | '+' | '.join(profiles)+' |','|---|'+'---|'*len(profiles)]
 for i,name in enumerate(names,1):
  code=f'{prefix}{i:02d}'
  links=[]
  for profile in profiles:
   c=next(x for x in m['captures'] if x['code']==code and x['profile']==profile)
   links.append(f"[{Path(c['path']).name}]({c['path']})")
  lines.append(f'| {code} {name} | '+' | '.join(links)+' |')
 lines.append('')
(p/'coverage.md').write_text('\n'.join(lines).rstrip()+'\n',encoding='utf-8')
