# Djob模块文档

## RDS结果产生依据

**recent_adb_wrong_code**: 最后一个adb的错误结果

adb结果判定:  
- < 0 错误结果
- = 0 正确 


**结果block**:normal_block,inner_job

**recent_img_res_list**: 最近一个结果block产生的结果集,normal_block中的img_tool结果或则inner_job 的结果
**recent_img_rpop_list**: 最近一个结果block被消耗的结果集


**switch_block**:结果block前面必须的是一个结果block


img_tool结果判定:
- = 1 img_tool执行失败
- = 0 正确 

**job_assessment_value**： djob执行结果

计算规则:

djob 执行到End 节点:

- 判断 recent_img_res_list 是否有值，没有表明当前djob不产生结果,会将job_assessment_value
设置为-32
- recent_img_res_list有值则获取recent_img_res_list最右侧(最后一个img_tool)结果,如果结果为1,表明img_tool执行失败，
会获取recent_adb_wrong_code，最为可能导致djob 执行错误的结果依据。若会获取recent_adb_wrong_code为空则
job_assessment_value为 1


djob 执行到fail 节点: job_assessment_value 设置成  1
djob 执行到success 节点: job_assessment_value 设置成  0

除此之外,eblock 抛出的异常会直接导致djob执行结果中断,并会 fake_rds.




## job flow 支持

结果unit的结果怎么存储。

性能用例的结果怎么计算（是否要有多个job flow）。

