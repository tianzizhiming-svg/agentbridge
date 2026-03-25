# Legal Disclaimer / 法律声明

> By using this service, you acknowledge that you have read, understood, and agree to be bound by this disclaimer.
>
> 使用本服务即表示您确认已阅读、理解并同意接受本声明的约束。

---

## Version History / 版本记录

| Version / 版本 | Date / 日期 | Changes / 变更说明 |
|----------------|-------------|-------------------|
| v1.0 | 2026-03-26 | Initial release / 首次发布 |

---

## 1. Applicable Law / 适用法律

AgentBridge operates under the legal framework of the People's Republic of China and complies with applicable international regulations, including but not limited to:

AgentBridge 在中华人民共和国法律框架下运营，同时遵守国际通行法律规范，包括但不限于：

- Cybersecurity Law of the People's Republic of China / 《中华人民共和国网络安全法》
- Data Security Law of the People's Republic of China / 《中华人民共和国数据安全法》
- Personal Information Protection Law of the People's Republic of China / 《中华人民共和国个人信息保护法》
- Measures for the Administration of Internet Information Services / 《互联网信息服务管理办法》
- EU General Data Protection Regulation (GDPR, applicable to European users) / 欧盟《通用数据保护条例》（GDPR，适用于欧洲用户）

---

## 2. How AgentBridge Works / 服务运作方式

AgentBridge is a **stateless data transmission tool**. The complete data flow is as follows:

AgentBridge 是一个**无状态数据传输工具**，完整数据流如下：

```
Target Website (WeChat / Zhihu / Baidu / etc.)
目标网站（微信 / 知乎 / 百度等）
    ↓
AgentBridge Server — HTTP fetch + JS rendering (Playwright)
AgentBridge 服务器 — HTTP 抓取 + JS 渲染（Playwright）
    ↓
HTML → Markdown (cleaned, not stored)
HTML → Markdown（清洗后传输，不落盘存储）
    ↓
Cloudflare Tunnel (traffic relay, see Section 6)
Cloudflare Tunnel（流量中转，见第6条）
    ↓
User's Agent / Program (via HTTPS)
用户的 Agent / 程序（通过 HTTPS 接收）
    ↓
User's own systems — storage, processing, and use
用户自有系统 — 存储、处理、使用
```

**AgentBridge does not store, cache, or retain any fetched content.** All responsibility for data handling after delivery lies solely with the user.

**AgentBridge 不存储、不缓存、不保留任何抓取内容。** 数据送达用户端后的一切处理责任由用户自行承担。

---

## 3. Permitted Content / 可抓取内容

Users may use this service to fetch the following types of publicly available content:

用户可使用本服务抓取以下类型的公开内容：

- Publicly published web content accessible without login / 无需登录即可访问的公开网页内容
- News, public commentary, and open academic materials / 新闻资讯、公开评论、公开学术资料
- Public data not involving personal privacy / 不涉及个人隐私的公开数据

---

## 4. Prohibited Content / 禁止抓取内容

The following content is **strictly prohibited** from being fetched or transmitted via this service:

以下内容**严格禁止**通过本服务抓取或传输：

1. **Personal and private information** — including but not limited to names, ID numbers, phone numbers, home addresses, and biometric data / **个人隐私信息** — 包括但不限于姓名、身份证号、手机号、家庭住址、生物特征等
2. **State secrets and sensitive data** — data related to national security, national defense, or diplomacy / **国家秘密及敏感数据** — 涉及国家安全、国防、外交等领域的数据
3. **Important data** — as defined under the Data Security Law, which may not be transferred cross-border without lawful authorization / **重要数据** — 依据《数据安全法》认定的重要数据，未经合法授权不得跨境传输
4. **Copyrighted content** — articles, images, audio, or video protected by copyright law without authorization from the rights holder / **受版权保护的内容** — 未经著作权人授权的文章、图片、音视频等
5. **Illegal content** — any content that violates Chinese law, including but not limited to content related to gambling, fraud, pornography, or terrorism / **违法违规内容** — 任何违反中国法律法规的内容，包括但不限于涉及赌博、诈骗、色情、恐怖主义的内容
6. **Login-protected content** — content accessible only after authentication, without proper authorization / **需登录才能访问的内容** — 未经授权抓取需身份验证才能访问的内容
7. **Content prohibited by the target platform** — content that violates the target website's robots.txt or terms of service / **平台明确禁止爬取的内容** — 违反目标网站 robots.txt 或服务条款禁止爬取的内容

---

## 5. Restricted Platforms / 受限平台说明

The following platforms explicitly prohibit automated scraping in their terms of service. Users must independently assess compliance risks before fetching content from these platforms:

以下平台在其服务条款中明确禁止自动化抓取，用户须自行评估合规风险：

| Platform / 平台 | Restriction / 限制说明 |
|----------------|----------------------|
| WeChat Official Accounts / 微信公众号 | Tencent ToS prohibits unauthorized scraping / 腾讯服务协议禁止未授权爬取 |
| Zhihu / 知乎 | User agreement prohibits automated collection / 用户协议禁止自动化采集 |
| Weibo / 微博 | Data access requires official API / 需通过官方 API 获取数据 |
| Douyin / TikTok, Kuaishou / 抖音 / 快手 | Explicitly prohibit third-party automated access / 明确禁止第三方自动化访问 |
| Taobao, JD.com / 淘宝 / 京东 | E-commerce data protected under anti-unfair competition law / 电商平台数据受反不正当竞争法保护 |

> ⚠️ Users must obtain lawful authorization or independently assess legal risk before using this service to fetch content from the above platforms. AgentBridge bears no legal liability arising therefrom.
>
> ⚠️ 用户在使用本服务抓取上述平台内容前，须自行获得合法授权或评估法律风险，AgentBridge 不承担因此产生的法律责任。

> Users seeking lawful authorization for access to these platforms should contact the platform's official business development or API program channels.
>
> 如需获得上述平台的合法授权，用户应联系平台官方商务合作或 API 计划渠道。

---

## 6. Network Infrastructure / 网络传输说明

This service uses **Cloudflare Tunnel** for traffic forwarding. User requests and response data pass through Cloudflare network nodes during transmission. Cloudflare's Privacy Policy applies to this transit process.

本服务使用 **Cloudflare Tunnel** 进行流量转发。用户请求及响应数据在传输过程中经由 Cloudflare 网络节点中转，Cloudflare 隐私政策适用于该传输过程。

AgentBridge is not responsible for data handling by Cloudflare network nodes. For details on Cloudflare's data processing practices, please refer to: https://www.cloudflare.com/privacypolicy/

AgentBridge 不对 Cloudflare 网络节点的数据处理行为承担责任。如需了解 Cloudflare 数据处理方式，请参阅：https://www.cloudflare.com/privacypolicy/

By using this service, users acknowledge and accept this transmission path.

用户在使用本服务前，应知悉并接受此传输路径。

---

## 7. Cross-border Data Transfer / 数据跨境传输

Under the Data Security Law and the Measures for Security Assessment of Cross-border Data Transfers:

依据《数据安全法》及《数据出境安全评估办法》：

- AgentBridge **does not actively store** any web content requested by users / AgentBridge **不主动存储**用户请求的任何网页内容
- Users are responsible for ensuring that any cross-border data transfer complies with Chinese data export regulations / 用户有责任确保其跨境传输的数据符合中国数据出境相关规定
- For cross-border transfers involving important data or large volumes of personal information, users must complete a security assessment or sign a standard contract as required by law / 涉及重要数据或大量个人信息的跨境传输，用户须依法完成安全评估或签订标准合同

---

## 8. Limitation of Liability / 免责条款

1. **User responsibility** — Users bear full legal responsibility for all fetch requests they initiate and for all uses of data obtained through this service / **用户自担责任** — 用户对其发起的所有抓取请求及所获取数据的使用方式承担全部法律责任
2. **Not legal advice** — This disclaimer does not constitute legal advice. Users should consult qualified legal counsel regarding their specific use cases / **不构成法律建议** — 本声明不构成法律意见，用户应就具体使用场景咨询专业法律顾问
3. **Service interruptions** — AgentBridge is not liable for service interruptions caused by target website anti-scraping mechanisms, network instability, or force majeure / **服务中断** — AgentBridge 不对因目标网站反爬机制、网络波动或不可抗力导致的服务中断承担责任
4. **Content accuracy** — AgentBridge makes no warranties regarding the accuracy, completeness, or timeliness of fetched content / **内容准确性** — AgentBridge 不对抓取内容的准确性、完整性或时效性作出任何保证
5. **Misuse** — If a user is found to be using the service in violation of laws or regulations, AgentBridge reserves the right to immediately terminate service and cooperate with relevant authorities / **滥用行为** — 若发现用户存在违法违规使用行为，AgentBridge 有权立即终止服务并配合相关部门调查
6. **Liability cap** — To the maximum extent permitted by law, AgentBridge's total liability shall not exceed the total fees paid by the user for the service in the preceding 12 months / **赔偿上限** — 在法律允许的最大范围内，AgentBridge 的累计赔偿责任不超过用户在过去 12 个月内为本服务支付的总费用

---

## 9. Compliance Recommendations / 合规使用建议

- Only fetch publicly available content that the target website explicitly permits or does not prohibit / 仅抓取目标网站明确允许或未禁止的公开内容
- Control fetch frequency to avoid placing excessive load on target servers / 控制抓取频率，避免对目标服务器造成过大压力
- Verify copyright ownership before using fetched content for commercial purposes / 不将抓取内容用于商业目的前，先确认版权归属
- For data involving personal information, fulfill legal notification obligations and obtain consent / 涉及个人信息的数据，需依法履行告知义务并取得同意

---

## 10. Contact / 联系方式

For any questions regarding this disclaimer, please contact us via X: [@manniusl](https://x.com/manniusl)

如对本声明有任何疑问，请通过 X 联系：[@manniusl](https://x.com/manniusl)

---

## 11. API Terms of Use / API 使用条款

By calling AgentBridge API endpoints, users agree to:

调用 AgentBridge API 接口即表示用户同意：

- Not use the service for any illegal, harmful, or abusive purposes / 不将本服务用于任何非法、有害或滥用目的
- Not attempt to bypass rate limits, payment requirements, or access controls / 不尝试绕过限速、支付要求或访问控制
- Not resell or redistribute the service without authorization / 未经授权不得转售或再分发本服务

Violation may result in immediate termination of API access without notice.

违反上述条款可能导致 API 访问权限被立即终止，恕不另行通知。

---

## 12. Planned Safeguards / 规划中的保障措施

To further enhance compliance and security, the following measures are under development:

为进一步加强合规与安全保障，以下措施正在规划中：

- robots.txt compliance check prior to fetch / 抓取前 robots.txt 合规检查
- User agreement acknowledgment during registration / 注册时用户协议强制确认
- Domain blacklist mechanism / 域名黑名单机制
- Regular log rotation and retention policy / 定期日志清理策略
- Anomalous request detection and blocking / 异常请求检测与拦截

*These measures will be implemented as service scale grows. / 上述措施将随服务规模增长逐步实施。*

---

*Last updated: March 2026 / 最后更新：2026 年 3 月*

*AgentBridge reserves the right to update this disclaimer at any time. / AgentBridge 保留随时更新本声明的权利。*
