# coding=utf-8

# 导入蓝图对象api
from . import api
# 导入图片验证码扩展包
from ihome.utils.captcha.captcha import captcha
# 导入redis数据库实例,常量文件,sqlalchemy实例
from ihome import redis_store,constants,db
# 导入flask内置的对象
from flask import current_app,jsonify,make_response,request,session
# 导入自定义的状态码
from ihome.utils.response_code import RET
# 导入模型类User
from ihome.models import User
# 导入云通讯接口,实现发送短信
from ihome.utils import sms

# 导入正则模块
import re
# 导入随机数模块
import random

@api.route('/imagecode/<image_code_id>',methods=['GET'])
def generate_image_code(image_code_id):
    """
    生成图片验证码
    1/调用captcha扩展包,生成图片验证码,name,text,image
    2/把图片验证码存入redis缓存中,设置过期时间
    3/返回图片验证码,需要设置响应类型
    :param image_code_id:
    :return:
    """
    # 调用captcha扩展包,生成图片验证码
    name,text,image = captcha.generate_captcha()
    # 把图片验证码存入redis数据库中
    try:
        redis_store.setex('ImageCode_' + image_code_id,constants.IMAGE_CODE_REDIS_EXPIRES,text)
    except Exception as e:
        # 记录错误日志信息
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='保存图片验证码失败')
    else:
        # 返回前端图片
        response = make_response(image)
        # 需要设置响应类型
        response.headers['Content-Type'] = 'image/jpg'
        # 返回结果
        return response


@api.route('/smscode/<mobile>',methods=['GET'])
def send_sms_code(mobile):
    """
    发送短信:获取参数/校验参数/业务处理/返回结果
    1/获取参数,mobile,text,id
    2/校验参数的完整性all/any
    3/校验手机号,正则表达式
    4/校验图片验证码,获取本地存储的真实图片验证码
    5/判断获取结果
    6/删除图片验证码
    7/比较图片验证码是否一致
    8/判断手机号是否已注册
    9/构造短信随机数,random.randint()
    10/发送短信,调用云通讯接口
    11/需要保存发送结果
    12/判断发送结果是否成功
    13/返回结果
    :param mobile:
    :return:
    """
    # 获取get请求的参数,mobile,text,id
    image_code = request.args.get('text')
    image_code_id = request.args.get('id')
    # 校验参数的完整性
    if not all([mobile,image_code,image_code_id]):
        return jsonify(errno=RET.PARAMERR,errmsg='参数不完整')
    # 校验手机号格式
    if not re.match(r'1[3456789]\d{9}$',mobile):
        return jsonify(errno=RET.PARAMERR,errmsg='手机号格式错误')



    # 校验图片验证码,获取本地真实的图片验证码
    try:
        real_image_code = redis_store.get('ImageCode_' + image_code_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询图片验证码失败')

    # 校验获取结果
    if not real_image_code:
        return jsonify(errno=RET.NODATA,errmsg='图片验证码过期')
    # 删除图片验证码,因为图片验证码只允许获取一次,即只能让用户比较一次
    try:
        redis_store.delete('ImageCode_' + image_code_id)
    except Exception as e:
        current_app.logger.error(e)
    # 比较图片验证码是否一致,忽略大小写
    if real_image_code.lower() != image_code.lower():
        return jsonify(errno=RET.DATAERR,errmsg='图片验证码不一致')
    # 生成短信随机码,格式化输出,确保生成的随机数为六位数
    sms_code = '%06d' % random.randint(1,999999)
    # 需要保存短信随机数
    try:
        redis_store.setex('SMSCode_' + mobile,constants.SMS_CODE_REDIS_EXPIRES,sms_code)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='保存短信验证码失败')
    # 判断手机号是否存在
    try:
        # 根据手机号进行查询,并判断查询结果
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询用户信息失败')
    else:
        # 判断用户存在
        if user is not None:
            return jsonify(errno=RET.DATAEXIST,errmsg='手机号已注册')
    # 调用云通讯接口,发送短信
    try:
        ccp = sms.CCP()
        # 保存发送结果
        result = ccp.send_template_sms(mobile,[sms_code,constants.SMS_CODE_REDIS_EXPIRES/60],1)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR,errmsg='发送短信异常')
    # 判断发送短信结果
    # if result == 0:
    if 0 == result:
        return jsonify(errno=RET.OK,errmsg='发送成功')
    else:
        return jsonify(errno=RET.THIRDERR,errmsg='发送失败')


@api.route('/users',methods=['POST'])
def register():
    """
    注册用户
    1/获取参数,user_data = request.get_json()获取请求体中的data数据
    2/校验参数存在
    3/获取详细的参数信息,mobile,sms_code,password
    4/校验参数的完整性
    5/校验手机号格式
    6/获取本地存储的真实短信验证码
    7/判断获取结果
    8/比较短信验证码是否一致
    9/删除短信验证码
    10/判断用户是否已注册
    11/保存用户信息,
    user = User(mobile=mobile,name=mobile)
    实际上调用了generate_password_hash()
    user.password = password
    12/提交数据到数据库,如果发生异常需要进行回滚
    13/缓存用户信息
    flask_session扩展包:实现用户信息缓存的位置,对session加密签名,指定过期时间;
    请求上下文对象session:用来从redis中获取缓存的用户信息
    session['user_id'] = user.id
    session.get('user_id')
    14/返回结果,返回附属信息user.to_dict()

    :return:
    """
    # 获取post参数,get_json()
    user_data = request.get_json()
    # 校验参数存在
    if not user_data:
        return jsonify(errno=RET.PARAMERR,errmsg='参数缺失')
    # 进一步获取详细的参数信息
    # user_data['mobile']
    mobile = user_data.get('mobile')
    smscode = user_data.get('sms_code')
    password = user_data.get('password')
    # 校验参数的完整性
    if not all([mobile,smscode,password]):
        return jsonify(errno=RET.PARAMERR,errmsg='参数不完整')
    # 对手机号进行校验
    if not re.match(r'1[3456789]\d{9}$',mobile):
        return jsonify(errno=RET.PARAMERR,errmsg='手机号格式错误')
    # 获取本地存储的真实短信验证码
    try:
        real_sms_code = redis_store.get('SMSCode_' + mobile)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='获取短信验证码失败')
    # 判断获取结果
    if not real_sms_code:
        return jsonify(errno=RET.NODATA,errmsg='短信验证码过期')
    # 比较短信验证码是否一致
    if real_sms_code != str(smscode):
        return jsonify(errno=RET.DATAERR,errmsg='短信验证码不一致')
    # 删除redis中存储的短信验证码
    try:
        redis_store.delete('SMSCode_' + mobile)
    except Exception as e:
        current_app.logger.error(e)
    # 判断用户是否已注册
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询用户信息失败')
    else:
        if user:
            return jsonify(errno=RET.DATAEXIST,errmsg='手机号已注册')
    # 保存用户信息
    user = User(name=mobile,mobile=mobile)
    # 调用了模型类中密码加密方法
    user.password = password
    # 提交数据到数据库中
    try:
        db.session.add(user)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        # 如果写入数据发生异常,需要进行回滚
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存用户信息失败')
    # 缓存用户信息到redis数据库中,需要使用请求上下文对象session
    session['user_id'] = user.id
    session['name'] = mobile
    session['mobile'] = mobile
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data=user.to_dict())




