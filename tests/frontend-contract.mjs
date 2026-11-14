import assert from 'node:assert/strict'
import {createServer} from 'vite'
import React from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
const server=await createServer({server:{middlewareMode:true}})
try {
 const {ComparisonTable,reportWarning,reportReferences}=await server.ssrLoadModule('/src/ReportPreview.tsx')
 const turn={question:'test',sections:[],evidence:[{paper:{id:'p',title:'Paper',author:'A',year:null,pages:2,summary:'用户提供，未外部核实'},page:2,excerpt:'Source',context:''}],taskStatus:'partial',verification:'with_warnings',audit:{comparison_table:[{cells:{finding:'Result [[1]]',cost:null},conditions:{dataset:'Small [[1]]'}}],unresolved:['Cost unknown']}}
 const html=renderToStaticMarkup(React.createElement(ComparisonTable,{turn,onCitation:()=>{}}))
 assert.match(html,/查看比较表引用 1/);assert.match(html,/未知\/未报告/);assert.match(html,/Small/)
 assert.equal(reportReferences(turn).length,1)
 assert.match(reportWarning(turn),/部分草稿/)
 assert.match(reportWarning({...turn,taskStatus:'blocked'}),/任务受阻/)
 assert.match(reportWarning({...turn,taskStatus:'completed',verification:'passed',audit:{report_version:2,evidence_snapshot_id:'s2',review:{reviewed_report_version:1,reviewed_evidence_snapshot_id:'s2'}}}),/版本不一致/)
 const store=new Map();globalThis.localStorage={getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v)}
 const api=await server.ssrLoadModule('/src/backend.ts')
 const project={id:'p',name:'P',folder:'C:/papers',knowledgePaths:['papers'],reviews:[]}
 const review={id:'r',question:'Question',history:[],referenceIds:[]}
 for(const mode of ['local','online','hybrid']){api.saveSources('p',{mode,query:'RAG',files:[{id:'upload-1',name:'p.pdf'}]});const request=api.reviewRequest(project,review);assert.equal(request.source_mode,mode);assert.deepEqual(request.project.knowledgePaths,mode==='online'?[]:['papers']);assert.deepEqual(request.uploaded_file_ids,mode==='online'?[]:['upload-1'])}
 globalThis.fetch=async(url,init)=>{assert.match(url,/api\/v2\/projects\/p\/uploads$/);assert.equal(init.headers.get('content-type'),'application/pdf');assert.equal(init.headers.get('Authorization'),'Bearer test');assert.ok(init.body instanceof Blob);return Response.json({file_id:'upload-test'})}
 assert.equal(await api.uploadPdf({url:'http://localhost:35549',token:'test',useDemo:false},'p',new File(['%PDF'],'p.pdf')),'upload-test')
 const {displayAgents,displayAgentStatus}=await server.ssrLoadModule('/src/workflow.ts')
 assert.equal(displayAgents.length,3)
 assert.equal(displayAgentStatus(displayAgents[0],{working:['search','analysis'],done:[]}), 'working')
 assert.equal(displayAgentStatus(displayAgents[0],{working:['analysis'],done:['search']}), 'working')
 api.saveSources('p',{mode:'local',query:'',files:[{id:'server-one',name:'one.pdf'}]},'http://localhost:1')
 assert.equal(api.readSources('p','http://localhost:2').files.length,0)
 const storedReport={sections:[{id:'unresolved',heading:'未解决问题',paragraphs:['Budget exhausted']}],evidence:[],task_status:'blocked',verification:'with_warnings',review:null,comparison_table:[],unresolved:['Budget exhausted'],usage:{model_calls:1},report_version:2,evidence_snapshot_id:'s2'}
 globalThis.fetch=async(url)=>{assert.match(url,/includeArtifacts=false/);return Response.json({id:'run',project_id:'p',conversation_id:'r',status:'completed',report:storedReport})}
 const recovered=await api.getBackendRun({url:'http://localhost:35549',useDemo:false},'run','p','r',new AbortController().signal)
 assert.equal(recovered.status,'completed');assert.equal(recovered.output.taskStatus,'blocked');assert.equal(recovered.output.audit.report_version,2);assert.deepEqual(recovered.output.audit.unresolved,['Budget exhausted'])
 console.log('PASS: comparison citations, null values, conditions, table-only bibliography, partial/blocked/version warnings, three source modes and raw authenticated PDF upload')
} finally {await server.close()}
