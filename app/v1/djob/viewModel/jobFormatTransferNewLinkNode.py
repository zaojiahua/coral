from app.execption.outer.error_code.djob import InnerJobUnedited
from app.v1.djob.config.setting import RESULT_TYPE


class JobFormatTransform:
    def __init__(self, ui_json):
        self.ui_json = ui_json

    def jobDataFormat(self):
        originaldata = self.ui_json
        jobNodeDict = {}
        jobLinkDict = {}
        for nodeDict in originaldata.get('nodeDataArray', []):

            if nodeDict.get('category', '') == 'Start':  # Start
                jobLinkDict['start'] = self.findNextKey(originaldata['linkDataArray'], nodeDict['key'])

            elif nodeDict.get('category', '') == 'Job':  # Job
                if nodeDict.get('jobLabel') is None:
                    raise InnerJobUnedited()
                jobNodeDict[str(nodeDict['key'])] = {'blockName': nodeDict.get('text'), 'nodeType': 'job',
                                                     'jobLabel': nodeDict['jobLabel'],
                                                     'jobId': nodeDict.get('jobId'),
                                                     'assistDevice': nodeDict.get('assistDevice')}
                jobLinkDict[str(nodeDict['key'])] = self.findNextLinkDict(originaldata, nodeDict['key'])

            elif nodeDict.get('category', '') == 'normalBlock':
                if 'unitLists' not in nodeDict or not nodeDict['unitLists']:  # 判断存在并不为空
                    return -1
                blockDict = dict(nodeType='normal')

                jobLinkDict[str(nodeDict['key'])] = self.findNextLinkDict(originaldata, nodeDict['key'])

                blockDict['execDict'] = dict(unitLists=self.getUnitLists(nodeDict.get('unitLists', '')),
                                             blockName=nodeDict.get('text')
                                             )

                jobNodeDict[str(nodeDict['key'])] = blockDict

            elif nodeDict.get('category', '') == 'switchBlock':
                blockDict = dict(
                    blockName=nodeDict.get('text'),
                    checkDicFile=nodeDict.get('fileName'),
                    nodeType='switch'
                )
                SwitchNextKeyDict = self.findSwitchNextKeyDict(originaldata['linkDataArray'], nodeDict['key'])
                for k, v in SwitchNextKeyDict.items():
                    value = self.checkEndORFailORSuccess(v, originaldata['nodeDataArray'])
                    SwitchNextKeyDict[k] = value if value is not None else v
                jobLinkDict[str(nodeDict['key'])] = self.switchNextLinkformat(SwitchNextKeyDict)
                jobNodeDict[str(nodeDict['key'])] = blockDict

        return dict(jobNodesDict=jobNodeDict, jobLinksDict=jobLinkDict)

    def switchNextLinkformat(self, switchNextKeyDictOld):
        """
        switch next node 新旧格式转换
        :param switchNextKeyDictOld:
        :return:
        """
        switchNextKeyDictNew = {}
        for k, v in switchNextKeyDictOld.items():
            switchNextKeyDictNew[k] = dict(nextNode=v)
        return switchNextKeyDictNew

    def getUnitLists(self, unitLists):
        """
        获取unitLists的内容并格式转换
        :param unitLists:
        :return:
        """
        UnitLists = []
        nextKey = '0'
        nodeDataArray = unitLists.get('nodeDataArray', [])
        linkDataArray = unitLists.get('linkDataArray', [])
        for unitList in nodeDataArray:
            if unitList.get('category') == 'Start':
                nextKey = str(unitList.get('key'))
                break
        for i in range(100):  # 遍历unitList按执行顺序放置到list中
            nextKey = self.findNextKey(linkDataArray, nextKey)
            if not self.isEnd(nextKey, nodeDataArray):
                tempUnitDict = self.getUnitList(nextKey, nodeDataArray)
                if tempUnitDict == -1:
                    return -1
                UnitLists.append(tempUnitDict)
            else:
                break
        return UnitLists

    def getUnitList(self, UnitListKey, nodeDataArray):
        unitDict = {'unitList': [], 'key': UnitListKey}
        for nodeDict in nodeDataArray:
            if str(nodeDict.get('group', '')) == UnitListKey:
                try:
                    tempDict = nodeDict.get('unitMsg', '')
                except:
                    return -1
                if tempDict.get('finalResult'):  # 适配，之前会有这一行，需要保证全部删除，再进行设置
                    del tempDict['finalResult']
                if nodeDict.get("star") == RESULT_TYPE:  # 对结果unit进行设置
                    tempDict['finalResult'] = True
                tempDict['jobUnitName'] = nodeDict.get('text', '')
                tempDict['key'] = nodeDict['key']
                unitDict['unitList'].append(tempDict)
        return unitDict

    def findReferDatDict(self, linkdata):
        """
        获取link上的referDatDict
        :param linkdata:
        :return:
        """
        if linkdata.get('referDatDict', None):
            return dict(checkDict=dict(referDatDict=linkdata.get('referDatDict')))

    def findNextLinkDict(self, originaldata, key):
        """
        通过当前key 获取指向的下一个key ,并将referDatDict保存下来  key 只能是normalBlock 的key
        :param originaldata:
        :param key:
        :param key:
        :return:
        """
        linkArray = originaldata.get('linkDataArray')
        for linkdata in linkArray:
            if str(key) == str(linkdata.get('from')):
                nextKey = str(linkdata.get('to'))
                result = self.checkEndORFailORSuccess(nextKey, originaldata['nodeDataArray'])
                nextNodeDict = dict(nextNode=result) if result else dict(nextNode=nextKey)

                referDatDict = self.findReferDatDict(linkdata)
                return dict(referDatDict, **nextNodeDict) if referDatDict else nextNodeDict

        print('warning:can not find the specific key in linkArray')
        raise Exception

    def findNextKey(self, linkArray, key):
        """
        根据当前key 获取指向的下一个key
        :param linkArray:
        :param key:
        :return:
        """
        for linkdata in linkArray:
            if str(key) == str(linkdata.get('from')):
                return str(linkdata.get('to'))
        print('warning:can not find the specific key in linkArray')
        raise Exception

    def findSwitchNextKeyDict(self, linkArray, key):
        keyList = {}
        for linkdata in linkArray:
            if str(key) == str(linkdata.get('from')):
                if not linkdata.get('text') or linkdata.get('text').strip() == 'else':
                    keyList['else'] = str(linkdata.get('to'))
                else:
                    keyList[linkdata.get('text').strip()] = str(linkdata.get('to'))

        return keyList

    def checkEndORFailORSuccess(self, blockKey, nodeDataArray):
        """

        :param blockKey:  判断 key 对应的 category 是否为 End
        :param nodeDataArray:
        :return:   None   end   fail success
        """
        if self.isEnd(blockKey, nodeDataArray):
            for nodeDict in nodeDataArray:
                if str(nodeDict['key']) == str(blockKey):
                    if nodeDict['text'] == 'End':
                        return 'end'
                    elif nodeDict['text'] == 'Fail':
                        return 'fail'
                    elif nodeDict['text'] == 'Success':
                        return 'success'

    def isEnd(self, blockKey, nodeDataArray):
        existEnd = False
        for nodeDict in nodeDataArray:
            if nodeDict.get('category', '') == 'End':
                existEnd = True
                if str(nodeDict['key']) == str(blockKey):
                    return True

        assert existEnd, (
            'warning:can not find End block in job-flow-dict'
        )


if __name__ == '__main__':
    from app.libs import jsonutil

    print(JobFormatTransform(jsonutil.read_json_file('ui.json')).jobDataFormat())
    jsonutil.dump_json_file(JobFormatTransform(jsonutil.read_json_file('ui.json')).jobDataFormat(), '2.json')
