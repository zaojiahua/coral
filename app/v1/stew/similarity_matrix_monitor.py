import copy
import itertools
import threading
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sklearn import preprocessing

from app.config.url import user_url, device_url, job_url, rds_large_amount_url
from app.execption.outer.error_code.total import RequestException
from app.libs.http_client import request
from app.libs.log import setup_logger


def register_stew_user():
    jsdata = {"username": "AITester", "password": "xuegao", "groups": ["Admin"]}
    try:
        res = request(method="POST", url=user_url, json=jsdata, error_log_hide=True)
    except RequestException:
        res = request(method="GET", url=user_url, params={"username": "AITester"})
        res = res.get("reefusers")[0]
    return res.get("id")


class DataCollectMonitor(threading.Thread):
    def __init__(self, user_id):
        super(DataCollectMonitor, self).__init__()
        self.user_id_exclude = str(user_id)
        self.logger = setup_logger('stew', r'stew.log')

    @staticmethod
    def get_all_device():
        param = {"fields": "device_label"}
        res = request(method="GET", url=device_url, params=param)
        device_list = [i.get("device_label") for i in res.get("devices")]
        return device_list

    @staticmethod
    def get_job_info(**kwargs):
        res = request(method="GET", url=job_url, params=kwargs)
        return res.get("jobs")

    @staticmethod
    def get_rds(**kwargs):
        kwargs["tboard__author_id!"] = kwargs["tboard__author_id"]
        del kwargs["tboard__author_id"]
        return request(method="GET", url=rds_large_amount_url, params=kwargs)


class SimilarityMatrixMonitor(DataCollectMonitor):
    _default_dict = {
        "job_para": {
            "fields": "job_label,test_area,test_area.description,author,author.username,recently_used_time,"
                      "earliest_used_time,phone_models,phone_models.phone_model_name,android_version,"
                      "android_version.version,rom_version,rom_version.version",
            "job_deleted": False,
            "job_type": "Joblib",
            "draft": False
        },
        "rdsPara": {
            "start_time__gt": str(datetime.now() - timedelta(days=5)),
            "end_time__lt": str(datetime.now()),
            "created_by_ai_tester": False,
            "job__job_deleted!": True,
        },
        "devicePara": {}
    }

    _useful_feature = {"author": "username", "test_area": "description"}
    _muti_item_name = "test_area"

    def __init__(self, *args):
        super(SimilarityMatrixMonitor, self).__init__(*args)
        self.keepNum = 5
        self.keepRun = True

    def run(self):
        while self.keepRun:
            try:
                self.device_id_list = self.get_all_device()
                self.job_feature_list = self.get_job_info(**(self._default_dict["job_para"]))
                if not self.job_feature_list:
                    self.logger.critical("【Critical】 cannot find any job to run 【Critical】")
                    break
                self.job_label_list = [job.get("job_label") for job in self.job_feature_list]
                rds_data = self.get_rds(**self._default_dict["rdsPara"], tboard__author_id=self.user_id_exclude)
                self.logger.debug("stew init ---1  get rds/job/device info success")
                self.similarity_matrix = self.calculate_matrix(rds_data, self.job_feature_list)
                self.job_feature_df = self.form_job_feature_matrix(self.job_feature_list)
                self.logger.debug("stew init ---2  get similarity_matrix/job_feature_df info success")
                self.deal_with_multi_item(self.job_feature_df.loc[:, self._muti_item_name].values, self._muti_item_name)
                self.deal_with_str_item(self.job_feature_df.loc[:, "author"], "author")
                self._deal_with_abnormal_item(self.job_feature_df)
                self.logger.debug("stew init ---3  data format finished")
                if self.job_label_list == -1 or self.device_id_list == -1 or self.job_feature_list == -1:
                    self.logger.error(f"get data from reef fail ")
            except Exception as e:
                self.logger.error(f"exception happen  info: {repr(e)}")
            finally:
                time.sleep(86400)

    def form_job_feature_matrix(self, job_feature_list):
        """
        :param job_feature_list: job attribute get from reef
        :return: df with index of device_label and columns of all feature in featureNameList
        eg:
                                                                  author                   test_area
            job-1911c35b-fb8d-47fa-9676-f6db02d341d5                  tingting                      [wifi]
            job-4a5977fa-c309-4984-9456-45b5f6b9ad00                  tingting                   [browser]
            job-removePhoneCall                       user-default000000000001                 [machBrain]
            job-a03de750-6739-4e35-8a31-5a60ca01cf8a  user-default000000000001                   [browser]
            job-fa6fe5c1-7bfa-4615-a74d-0a43c100a399                  tingting           [machBrain, wifi]
            job-f20c2da7-2fed-49d8-93a8-1afbf0780f13                  tingting                      [wifi]
            job-e7a0a491-c1ab-4159-a806-c62796d4cd98  user-default000000000001                 [machBrain]

        """
        feature_matrix = []
        for job in job_feature_list:
            inside_list = []
            for feature, name in self._useful_feature.items():
                if isinstance(job.get(feature), list):
                    content = [i.get(name).strip() for i in job.get(feature)]
                else:
                    author = job.get(feature)
                    content = author.get(name).strip() if author is not None else None
                inside_list.append(content)
            feature_matrix.append(inside_list)
        return pd.DataFrame(feature_matrix, index=self.job_label_list, columns=self._useful_feature)

    def calSpecificValue(self, deviceID, filted_matrix, backup_Job_list):
        """
        :return: jobID in a list
        """
        if hasattr(self, "similarity_matrix") and backup_Job_list:
            ranking_job_list = self.get_predict(self.device_id_list.index(deviceID), filted_matrix, backup_Job_list,
                                                reduction=False)
            self.logger.debug(f"calculated job list & score: {ranking_job_list}")
            self.logger.debug(f"back up job list: {backup_Job_list}")
            # not write cal's value back to matrix
            for job_tuple in ranking_job_list:
                job_index = self.job_label_list.index(backup_Job_list[job_tuple[0]])
                self.similarity_matrix[self.device_id_list.index(deviceID)][job_index] = job_tuple[1]
            if len(ranking_job_list) <= self.keepNum:
                return [backup_Job_list[jobTuple[0]] for jobTuple in ranking_job_list]
            else:
                return [backup_Job_list[jobTuple[0]] for jobTuple in ranking_job_list[: self.keepNum]]
        else:
            return -1

    def find_suitable_job(self, **kwargs):
        """
        a filter for  all jobs with attribute
        :param kwargs:  {"phone_models": "dior"
                    "android_version": "7.7.7"}
        :return:

        """
        _search_variable_name = {"phone_models": "phone_model_name",
                                 "rom_version": "version",
                                 "android_version": "version",
                                 "author": "username",
                                 "test_area": "description"}
        try:
            job_feature_list_copy = copy.deepcopy(self.job_feature_list)
            for job in self.job_feature_list:  # each job
                for key, value in kwargs.items():  # each attribute
                    inside_name = _search_variable_name.get(key)
                    attribute_list = [item.get(inside_name) for item in job.get(key)]
                    if value not in attribute_list:
                        # remove job from job_feature_list_copy which attribute not suitable
                        job_feature_list_copy.remove(job)
                        break
            back_up_job_list = [job.get("job_label") for job in job_feature_list_copy]
            self.logger.info(f"[bug point2.5] get back_up_job_list :{back_up_job_list}")
            if not back_up_job_list:
                self.logger.warning(f"---Warrning---:Do not have any job suit for a device due to device attribute "
                                    f"inconformity: {kwargs} ")
            tmp_matrix = [self.similarity_matrix[:, self.job_label_list.index(job)] for job in back_up_job_list]
            self.logger.info(f"[bug point2.8] get tmp_matrix :{tmp_matrix}")
            return np.array(tmp_matrix).T, back_up_job_list
        except Exception as e:
            self.logger.error(f"exception happen in filter job ,info: {repr(e)}")
            return [], []

    def calculate_matrix(self, rds_data_list, job_feature_list):
        # todo modify this function for adding job-lifetime and deltT into matrix
        """
        :return: with shape of (device_num * job_num)
        """
        rds_data_list = rds_data_list.get("rdss")
        matrix = np.zeros(shape=(len(self.device_id_list), len(self.job_label_list)))
        for rds in rds_data_list:
            device_label = rds.get("device").get("device_label")
            job_label = rds.get("job").get("job_label")
            if job_label not in self.job_label_list:  # remove deleted&sysJob
                continue
            job_index = self.job_label_list.index(job_label)
            job_first_use_time = job_feature_list[job_index].get("earliest_used_time")
            job_last_using_time = job_feature_list[job_index].get("recently_used_time")
            if job_last_using_time is None or job_first_use_time is None:
                continue
            rds_create_time = rds.get("start_time")
            matrix[self.device_id_list.index(device_label)][job_index] += self.cal_time_weight(job_first_use_time,
                                                                                               job_last_using_time,
                                                                                               rds_create_time)
        return matrix

    def cal_time_weight(self, job_first_use_time, job_last_using_time, rds_create_time):
        # todo verify this function when back to company
        k = 1  # auto set this k&a when we have feedback data
        a = 4
        job_time_interval = (self.strftTime(job_last_using_time) - self.strftTime(rds_create_time))
        job_life_time = (self.strftTime(job_last_using_time) - self.strftTime(job_first_use_time))
        return k * np.exp(a * (-job_time_interval / (job_life_time + timedelta(seconds=1))))

    def strftTime(self, timeStr):
        return datetime.strptime(timeStr, "%Y-%m-%d %H:%M:%S")

    def get_predict(self, device_id_index, data_matrix, job_id_list, reduction=False):
        """
        :return: [(job_index,score)]
        """
        unrated_job_index_list = np.nonzero(data_matrix[device_id_index, :] == 0)[0]
        self.logger.info("try to calculate for job list:" + str(unrated_job_index_list))
        if len(unrated_job_index_list) == 0:
            job_list = list(zip(range(len(job_id_list)), data_matrix[device_id_index]))
            job_list.sort(key=lambda x: x[1], reverse=True)
            return job_list
        if reduction:
            self.logger.info("start to reduction by SVD method due to the similarity matrix is too big")
            svdMatrix = self.get_svd_matrix(data_matrix)
            job_list = []
            for jobIndex in unrated_job_index_list:
                score = self.get_score_for_job(jobIndex, device_id_index, data_matrix.T, svd_matrix=svdMatrix)
                job_list.append((jobIndex, score))
        else:
            job_list = []
            for jobIndex in unrated_job_index_list:
                if all(data_matrix[:, jobIndex] == 0):  # cold boot
                    score = self.cal_sim_by_feature(self.job_feature_df, jobIndex, self.similarity_matrix.T,
                                                    device_id_index, job_id_list)
                else:
                    score = self.get_score_for_job(jobIndex, device_id_index, data_matrix.T)
                job_list.append((jobIndex, score))
        exist_score_list = [(i, data_matrix[device_id_index][i]) for i in range(len(data_matrix[device_id_index])) if
                            i not in unrated_job_index_list]
        self.logger.debug(f"calculate job list:{job_list},exist_score_list:{exist_score_list} ")
        job_list.extend(exist_score_list)
        job_list.sort(key=lambda x: x[1], reverse=True)
        return job_list

    def get_svd_matrix(self, origin_matrix):
        """
        :param origin_matrix: (device_num*job_num)
        :return: (job_num*k)
        """
        u, sigma, v = np.linalg.svd(origin_matrix)
        k = self.sigma_percent(sigma, 0.90)
        m2 = np.mat(np.eye(k) * sigma[:k])  # broadcast
        return np.dot(np.dot(origin_matrix.T, u[:, :k]), m2.I)

    @staticmethod
    def sigma_percent(sigma, percentage):
        assert percentage <= 1.0, "percentage for singular value should lower than 1.0"
        sumsgm = sum(sigma ** 2)
        sumsgm2 = 0
        k = 0
        for i in sigma:
            sumsgm2 += i ** 2
            k += 1
            if sumsgm2 >= sumsgm * percentage:
                return k
        return 0

    def get_score_for_job(self, jobID, device_id_index, matrix, svd_matrix=None):
        """
        :param matrix: original data matrix with shape (job_num*device_num)
        :param method: different method for cal  similarity:cos_sim,corr_coef,l2_distance
        :param svd_matrix: matrix after SVD reduction with shape (job_num*k)
        """
        reduction_matrix = svd_matrix if svd_matrix else matrix
        dimension = matrix.shape[0]
        assert dimension >= 3, "Total job number should bigger than 3"
        similarity_dict = {}
        for job in range(dimension):
            if matrix[job][device_id_index] == 0 or job == jobID:
                continue
            similarity = self.cal_sim(reduction_matrix[job, :], reduction_matrix[jobID, :], method="cosSim")
            similarity_dict[similarity] = job
        return self.get_score(similarity_dict, reduction_matrix, device_id_index)

    def cal_sim_by_feature(self, df, job_index, data_matrix, device_id_Index, job_id_list):
        similarity_dict = {}
        for i in range(df.shape[0]):
            if i == job_index:
                continue
            similarity = self.cal_sim(df.iloc[i, :].values, df.loc[job_id_list[job_index], :].values, method="cosSim")
            similarity_dict[similarity] = i
        return self.get_score(similarity_dict, data_matrix, device_id_Index)

    @staticmethod
    def cal_sim(vector_1, vector_2, method="cos_sim"):
        if method == "corr_coef":
            return 0.5 + 0.5 * np.corrcoef(vector_1, vector_2)[0][1]
        elif method == "cos_sim":
            return 0.5 + 0.5 * np.dot(vector_1, vector_2.T) / (np.linalg.norm(
                vector_1) * np.linalg.norm(vector_2) + 0.0000001)
        elif method == "l2_distance":
            return 1.0 / (1.0 + np.linalg.norm(vector_1 - vector_2))
        else:
            return -1

    @staticmethod
    def get_score(similarity_dict, original_matrix, dimension_2, keep_n=3):
        score = 0
        top_njob_dict = {key: similarity_dict[key] for key in sorted(similarity_dict.keys(), reverse=True)[:keep_n]}
        for weight, index in top_njob_dict.items():
            score += original_matrix[index][dimension_2] * weight
        return round(score / keep_n, 3)

    def deal_with_multi_item(self, feature_list, feature_name):
        """
        :param feature_list: 2d-ndarray
        after change:
                                                    author  ...  have_Calendar    have_camera ....
        job-1911c35b-fb8d-47fa-9676-f6db02d341d5   tingting  ...              0           1
        job-4a5977fa-c309-4984-9456-45b5f6b9ad00   tingting  ...              0           0
        """
        # list all feature's name
        all_item_list = list(itertools.chain.from_iterable(feature_list))
        for name in set(all_item_list):
            # set 1 if this line have this feature
            featurValue = [1 if name in i else 0 for i in feature_list]
            self.job_feature_df = pd.concat(
                [self.job_feature_df, pd.DataFrame({"have_" + name: featurValue}, index=self.job_label_list)],
                join="outer", axis=1)
        self.job_feature_df = self.job_feature_df.drop(feature_name, axis=1)

    def deal_with_str_item(self, series, colunm_name):
        """
        after change:
                                                    author  ...  have_Calendar    have_camera ....
        job-1911c35b-fb8d-47fa-9676-f6db02d341d5     0  ...              0           1
        job-4a5977fa-c309-4984-9456-45b5f6b9ad00     0  ...              0           0
        """
        series = self.fill_in_blank_with_mode(series)
        if len(set(series.values)) <= 5:
            dummyColumn = pd.get_dummies(series, prefix=colunm_name)
        else:
            dummyColumn = pd.factorize(series)[0]
        self.job_feature_df = pd.concat([self.job_feature_df, dummyColumn], axis=1, join="outer")
        self.job_feature_df = self.job_feature_df.drop(colunm_name, axis=1)

    def fill_in_blank_with_mode(self, series):
        if len(series[series.isnull()].values) > 0:
            self.logger.warning(f"find blank feature fill in with mode,{series}")
            series = series.copy()
            series[series.isnull()] = series.dropna().mode().values[0]
        return series

    @staticmethod
    def _deal_with_abnormal_item(df):
        # del value(num) which is bigger than 2*std
        for column, std in df.std().items():
            df = df.drop(df[abs(df[column] - df.mean()[column]) >= 2 * std].index, axis=0)
        return df

    @staticmethod
    def _deal_with_continuous_data(series, type="scaling"):
        # scaling or binning data
        if type == "scaling":
            scaler = preprocessing.StandardScaler()
            return scaler.fit_transform(series.values.reshape(-1, 1))
        elif type == "binning":
            return pd.qcut(series, 5, labels=False)
        else:
            pass
