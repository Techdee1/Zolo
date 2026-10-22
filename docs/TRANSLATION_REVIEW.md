# Translation review

**Status: DRAFTS. None of the four translations has been checked by a native speaker.** They were
written to be short and plain, in the same register as the English, but tone marks, word choice and
tone all need a fluent reader before the demo (the PRD requires this). Pidgin follows the PRD's own
draft lines where it gave them.

How to review: read the sentence aloud the way it will be heard, check it says the same thing as the
English **and no more**, and correct it in `frontend/messages/<code>.json` (`pcm`, `yo`, `ha`, `ig`).
The `{placeholders}` must stay exactly as they are: a test fails if one is lost or renamed.

What is not translated on purpose: the landing page (English only), the demo console, the brand line
"for Zenith Bank", and the amount in words ("fifteen thousand naira"), which stays English in every
language until there are native-reviewed number words (row 4a in `PRD_DEVIATIONS.md`).

## Review these first

Sentences where a wrong word could make someone think money moved when it did not, or the reverse.


### Safety: nothing was sent

| Key | English | Pidgin | Yorùbá | Hausa | Igbo |
| --- | --- | --- | --- | --- | --- |
| `result.declined` | Declined. Nothing was sent. | You don decline. We no send anything. | O kọ̀. A kò fi nǹkan kankan ránṣẹ́. | Ka ƙi. Ba a aika komai ba. | Ị jụrụ. Anyị zigaghị ihe ọ bụla. |
| `result.expired` | This request expired. Nothing was sent. | This request don expire. We no send anything. | Ìbéèrè yìí ti parí. A kò fi nǹkan kankan ránṣẹ́. | Wannan buƙata ta ƙare. Ba a aika komai ba. | Arịrịọ a agwụla. Anyị zigaghị ihe ọ bụla. |
| `result.changed` | This payment changed after you heard it. Nothing was sent. | This payment change after you hear am. We no send anything. | Ìsanwó yìí yípadà lẹ́yìn tí o gbọ́ ọ. A kò fi nǹkan kankan ránṣẹ́. | Wannan biyan ya canza bayan ka ji shi. Ba a aika komai ba. | Ịkwụ ụgwọ a gbanwere mgbe ị nụchara ya. Anyị zigaghị ihe ọ bụla. |
| `result.changedBody` | Do not pay. Ask the agent to start again. | No pay. Tell the agent make e start again. | Má ṣe san án. Sọ fún aṣojú kí ó bẹ̀rẹ̀ lẹ́ẹ̀kan sí i. | Kada ka biya. Ka gaya wa wakili ya sake farawa. | Ekwela ụgwọ. Gwa onye nnọchi anya ka ọ malite ọzọ. |
| `result.failed` | The payment did not go through. Nothing was sent. | The payment no go through. We no send anything. | Ìsanwó náà kò lọ. A kò fi nǹkan kankan ránṣẹ́. | Biyan bai tafi ba. Ba a aika komai ba. | Ịkwụ ụgwọ ahụ agaghị. Anyị zigaghị ihe ọ bụla. |
| `result.limit` | This is over your limit. Nothing was sent. | This one pass your limit. We no send anything. | Èyí ti kọjá ààlà rẹ. A kò fi nǹkan kankan ránṣẹ́. | Wannan ya wuce iyakarka. Ba a aika komai ba. | Nke a gafere oke gị. Anyị zigaghị ihe ọ bụla. |
| `result.blocked` | We stopped this payment to keep your money safe. Nothing was sent. | We stop this payment to protect your money. We no send anything. | A dá ìsanwó yìí dúró láti dáàbò bo owó rẹ. A kò fi nǹkan kankan ránṣẹ́. | Mun dakatar da wannan biyan don kare kuɗinka. Ba a aika komai ba. | Anyị kwụsịrị ịkwụ ụgwọ a iji chebe ego gị. Anyị zigaghị ihe ọ bụla. |
| `result.rejected` | The bank did not accept this payment. Nothing was sent. | The bank no accept this payment. We no send anything. | Báńkì kò gba ìsanwó yìí. A kò fi nǹkan kankan ránṣẹ́. | Banki bai karɓi wannan biyan ba. Ba a aika komai ba. | Ụlọ akụ anabataghị ịkwụ ụgwọ a. Anyị zigaghị ihe ọ bụla. |
| `review.cancelled` | Cancelled. Nothing was sent. You can try again. | You cancel am. We no send anything. You fit try again. | O fagilé e. A kò fi nǹkan kankan ránṣẹ́. O lè tún gbìyànjú. | An soke. Ba a aika komai ba. Za ka iya sake gwadawa. | Ị kagburu ya. Anyị zigaghị ihe ọ bụla. Ị nwere ike ịnwale ọzọ. |
| `review.notYou` | We could not confirm it was you. Nothing was sent. Try again. | We no fit confirm say na you. We no send anything. Try again. | A kò lè jẹ́rìí pé ìwọ ni. A kò fi nǹkan kankan ránṣẹ́. Gbìyànjú lẹ́ẹ̀kan sí i. | Ba mu iya tabbatar kai ne ba. Ba a aika komai ba. Sake gwadawa. | Anyị enweghị ike ịkwado na ọ bụ gị. Anyị zigaghị ihe ọ bụla. Nwaa ọzọ. |
| `errors.network` | No connection. Nothing was sent. Try again. | No network. We no send anything. Try again. | Kò sí ìkànnì. A kò fi nǹkan kankan ránṣẹ́. Gbìyànjú lẹ́ẹ̀kan sí i. | Babu hanyar sadarwa. Ba a aika komai ba. Sake gwadawa. | Enweghị netwọk. Anyị zigaghị ihe ọ bụla. Nwaa ọzọ. |
| `errors.generic` | Something went wrong. Nothing was sent. Try again. | Something spoil. We no send anything. Try again. | Nǹkan kan ṣẹlẹ̀. A kò fi nǹkan kankan ránṣẹ́. Gbìyànjú lẹ́ẹ̀kan sí i. | Wani abu ya faru. Ba a aika komai ba. Sake gwadawa. | Ihe mere. Anyị zigaghị ihe ọ bụla. Nwaa ọzọ. |

### Safety: not paid yet

| Key | English | Pidgin | Yorùbá | Hausa | Igbo |
| --- | --- | --- | --- | --- | --- |
| `result.processing` | Processing. Don't hand over goods yet. | We dey process am. No give person im goods yet. | À ń ṣe é lọ́wọ́. Má ṣe fún ẹnikẹ́ni ní ẹrù rẹ̀ sibẹ̀. | Ana aiwatarwa. Kada ka ba da kayan tukuna. | Anyị na-arụ ọrụ na ya. Ejila ngwaahịa nye onye ọ bụla ugbu a. |
| `result.processingBody` | You approved {amount} to {payee}. We are waiting for the bank to confirm. This screen updates by itself. | You approve {amount} to {payee}. We dey wait make bank confirm. This screen go update by itself. | O fọwọ́ sí {amount} fún {payee}. À ń dúró kí báńkì jẹ́rìí rẹ̀. Ojú ìkànnì yìí yóò ṣe ara rẹ̀ ní àtúnṣe. | Ka amince da {amount} ga {payee}. Muna jiran banki ya tabbatar. Wannan allon zai sabunta kansa. | Ị kwadoro {amount} nye {payee}. Anyị na-echere ka ụlọ akụ kwenye. Ihuenyo a ga-emelite onwe ya. |
| `agent.processing` | Processing. Don't hand over goods yet. | We dey process am. No give person im goods yet. | À ń ṣe é lọ́wọ́. Má ṣe fún ẹnikẹ́ni ní ẹrù rẹ̀ sibẹ̀. | Ana aiwatarwa. Kada ka ba da kayan tukuna. | Anyị na-arụ ọrụ na ya. Ejila ngwaahịa nye onye ọ bụla ugbu a. |
| `agent.processingBody` | The customer approved. The bank has not confirmed yet. Wait for Paid. | The customer don approve. Bank never confirm. Wait make you see Paid. | Oníbàárà ti fọwọ́ sí i. Báńkì kò tíì jẹ́rìí rẹ̀. Dúró de A ti san án. | Abokin ciniki ya amince. Banki bai tabbatar ba tukuna. Jira An biya. | Onye ahịa kwadoro. Ụlọ akụ ekwenyebeghị. Chere Akwụọla ụgwọ. |
| `agent.waitForPaid` | Give cash only after you see Paid. | Give cash only when you see Paid. | Fún owó nìkan lẹ́yìn tí o bá rí A ti san án. | Ka ba da kuɗi sai bayan ka ga An biya. | Nye ego naanị mgbe ị hụrụ Akwụọla ụgwọ. |

### Success: money moved

| Key | English | Pidgin | Yorùbá | Hausa | Igbo |
| --- | --- | --- | --- | --- | --- |
| `result.paid` | Paid. You sent {amount} to {payee}. | E don pay. You don send {amount} to {payee}. | A ti san án. O fi {amount} ránṣẹ́ sí {payee}. | An biya. Ka aika {amount} ga {payee}. | Akwụọla ụgwọ. Ị zigara {amount} nye {payee}. |
| `result.paidBody` | The money has left your account. | The money don comot your account. | Owó náà ti kúrò nínú àkọọ́lẹ̀ rẹ. | Kuɗin ya fita daga asusunka. | Ego ahụ esila n'akaụntụ gị pụọ. |
| `agent.paidAnnounce` | Paid. {amountWords} from the customer. You can give the cash. | E don pay. {amountWords} from the customer. You fit give the cash. | A ti san án. {amountWords} láti ọ̀dọ̀ oníbàárà. O lè fún un ní owó. | An biya. {amountWords} daga abokin ciniki. Za ka iya ba da kuɗin. | Akwụọla ụgwọ. {amountWords} sitere n'aka onye ahịa. Ị nwere ike inye ego ahụ. |

### The rule: never ask for a PIN

| Key | English | Pidgin | Yorùbá | Hausa | Igbo |
| --- | --- | --- | --- | --- | --- |
| `passkey.never` | Zolo never asks for your PIN or your card number. | Zolo no dey ever ask for your PIN or your card number. | Zolo kì í béèrè PIN rẹ tàbí nọ́ńbà káàdì rẹ láé. | Zolo ba ya taɓa tambayar PIN ɗinka ko lambar katinka. | Zolo adịghị ajụ PIN gị ma ọ bụ nọmba kaadị gị ma ọlị. |
| `passkey.what` | A passkey lets you approve payments with your fingerprint, face or screen lock. | Passkey go let you approve payment with your fingerprint, face or screen lock. | Passkey jẹ́ kí o lè fọwọ́ sí ìsanwó pẹ̀lú ìka ọwọ́, ojú tàbí ìdè ẹ̀rọ rẹ. | Passkey yana ba ka damar amincewa da biyan kuɗi da yatsa, fuska ko makullin allo. | Passkey na-enye gị ohere ikwado ịkwụ ụgwọ site na mkpịsị aka, ihu ma ọ bụ mkpọchi ihuenyo gị. |
| `passkey.private` | Set your screen lock in private. Use earphones if you can. | Set your screen lock where person no dey see. Use earphone if you fit. | Ṣètò ìdè ẹ̀rọ rẹ níbi tí ẹnikẹ́ni kò ti rí ọ. Lo ẹ̀rọ ìgbọ́ràn tí o bá lè. | Saita makullin allonka a asirce. Yi amfani da belun kunne idan za ka iya. | Debe mkpọchi ihuenyo gị n'ezoghị ọnụ. Jiri ihe ntị ma ọ bụrụ na ị nwere ike. |

### Approving: what people tap and hear

| Key | English | Pidgin | Yorùbá | Hausa | Igbo |
| --- | --- | --- | --- | --- | --- |
| `review.title` | {payee} is asking for {amount} | {payee} dey ask for {amount} | {payee} ń béèrè fún {amount} | {payee} yana neman {amount} | {payee} na-arịọ {amount} |
| `review.approve` | Approve {amount} | Approve {amount} | Fọwọ́ sí {amount} | Amince da {amount} | Kwado {amount} |
| `review.approveWait` | Listen to the request first. | First listen to the request. | Kọ́kọ́ gbọ́ ìbéèrè náà. | Ka fara sauraron buƙatar. | Buru ụzọ gee arịrịọ ahụ ntị. |
| `review.decline` | Decline | No, decline am | Kọ̀ | Ƙi | Jụ |
| `review.askPasskey` | Check your fingerprint, face or screen lock. | Check your fingerprint, face or screen lock. | Lo ìka ọwọ́, ojú tàbí ìdè ẹ̀rọ rẹ. | Yi amfani da yatsa, fuska ko makullin allo. | Jiri mkpịsị aka, ihu ma ọ bụ mkpọchi ihuenyo gị. |
| `review.hearAgain` | Hear again | Hear am again | Gbọ́ lẹ́ẹ̀kan sí i | Sake ji | Nụọ ọzọ |

### Entering the code

| Key | English | Pidgin | Yorùbá | Hausa | Igbo |
| --- | --- | --- | --- | --- | --- |
| `pay.label` | The agent's 4-digit code | The agent 4-digit code | Kóòdù oní-nọ́ńbà mẹ́rin ti aṣojú | Lambar lamba huɗu ta wakili | Koodu ọnụọgụ anọ nke onye nnọchi anya |
| `pay.hint` | Ask the agent to read you the 4 digits on their screen. | Ask the agent make e read the 4 digits for im screen give you. | Bi aṣojú láti kà àwọn nọ́ńbà mẹ́rin tó wà lórí ìkànnì rẹ̀ fún ọ. | Ka roƙi wakili ya karanta maka lambobi huɗun da ke kan allonsa. | Gwa onye nnọchi anya ka ọ gụọ gị ọnụọgụ anọ ndị dị na ihuenyo ya. |
| `pay.notFound` | No request has that code. Check the 4 digits with the agent. | No request get that code. Check the 4 digits with the agent. | Kò sí ìbéèrè tó ní kóòdù yìí. Ṣàyẹ̀wò nọ́ńbà mẹ́rin náà pẹ̀lú aṣojú. | Babu buƙatar da ke da wannan lambar. Duba lambobi huɗun tare da wakili. | Enweghị arịrịọ nwere koodu a. Lelee ọnụọgụ anọ ahụ ya na onye nnọchi anya. |
| `pay.expired` | That code has expired. Ask the agent for a new one. | That code don expire. Ask the agent for new one. | Kóòdù yìí ti parí. Bi aṣojú fún tuntun. | Wannan lambar ta ƙare. Ka roƙi wakili ya ba ka sabuwa. | Koodu a agwụla. Rịọ onye nnọchi anya maka nke ọhụrụ. |

### Time

| Key | English | Pidgin | Yorùbá | Hausa | Igbo |
| --- | --- | --- | --- | --- | --- |
| `common.oneMinute` | One minute left. | One minute remain. | Ìṣẹ́jú kan ló kù. | Saura minti ɗaya. | Otu nkeji fọdụrụ. |
| `common.fifteenSeconds` | Fifteen seconds left. | Fifteen seconds remain. | Ìṣẹ́jú-àáyá mẹ́ẹ̀dógún ló kù. | Saura daƙiƙa goma sha biyar. | Sekọnd iri na ise fọdụrụ. |
| `common.timeUp` | Time is up. | Time don finish. | Àkókò ti parí. | Lokaci ya ƙare. | Oge agwụla. |

## Sign-off

| Language | Reviewer | Date | Notes |
| --- | --- | --- | --- |
| Pidgin | | | |
| Yorùbá | | | |
| Hausa | | | |
| Igbo | | | |
