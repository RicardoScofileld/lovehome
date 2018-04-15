# coding=utf-8

# 导入蓝图对象api
from . import api
# 导入redis数据库实例,常量文件,sqlalchemy实例
from ihome import redis_store,constants,db
# 导入flask内置的对象
from flask import current_app,jsonify,g,request,session
# 导入模型类
from ihome.models import Area,House,Facility,HouseImage,User,Order
# 导入自定义的状态码
from ihome.utils.response_code import RET
# 导入登陆验证装饰器
from ihome.utils.commons import login_required
# 导入七牛云
from ihome.utils.image_storage import storage
# 导入json模块
import json
# 导入datetime模块,对日期进行格式转换
import datetime


@api.route('/areas',methods=['GET'])
def get_area_info():
    """
    获取城区信息:缓存-----磁盘------缓存
    1/尝试从redis缓存数据库中获取区域信息
    2/获取区域信息,如果发生异常,需要把查询结果重新置为None值
    3/判断获取结果
    4/留下访问访问缓存区域信息的记录
    5/缓存中区域信息已经是json字符串,可以直接返回结果
    6/查询mysql数据库,获取区域信息
    7/校验查询结果
    8/定义容器,存储查询结果,遍历区域信息,
    9/转换成json字符串,存入redis缓存中
    areas_json = json.dumps(areas_list)
    10/返回结果
    resp = '{"errno":0,"errmsg":"OK","data":%s}' % areas_json
    return resp

    :return:
    """
    # 尝试从redis缓存中获取区域信息
    try:
        areas = redis_store.get('area_info')
    except Exception as e:
        current_app.logger.error(e)
        # 如果获取区域失败,需要把获取结果重新置为None
        # areas = None
        # return jsonify(errno=RET.OK,errmsg='OK')
    # 判断获取结果,如果有数据,留下访问缓存中区域信息的记录
    if areas:
        current_app.logger.info('hit area info redis')
        return '{"errno":0,"errmsg":"OK","data":%s}' % areas
    # 查询mysql数据库
    try:
        areas = Area.query.all()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='获取区域信息失败')
    # 校验查询结果
    if not areas:
        return jsonify(errno=RET.NODATA,errmsg='无区域信息')
    # 定义列表,存储查询结果
    areas_list = []
    for area in areas:
        areas_list.append(area.to_dict())
    # 序列化数据,准备存入缓存中
    areas_json = json.dumps(areas_list)
    # 把区域信息存入redis中
    try:
        redis_store.setex('area_info',constants.AREA_INFO_REDIS_EXPIRES,areas_json)
    except Exception as e:
        current_app.logger.error(e)
    # 构造响应数据
    resp = '{"errno":0,"errmsg":"OK","data":%s}' % areas_json
    # 返回结果
    return resp


@api.route('/houses',methods=['POST'])
@login_required
def save_house_info():
    """
    保存房屋信息
    1/获取用户信息,user_id
    2/获取参数,post请求的data数据get_json()
    3/校验参数存在
    4/获取详细的房屋基本配置参数信息(除房屋配套设施外的参数)
    5/校验参数的完整性
    6/对价格参数进行转换,由元转成分
    7/构造模型类对象,准备保存房屋数据
    8/尝试获取配套设施参数信息
    9/如果有配套设施,对设施编号进行过滤查询,确保前端传入的配套设施存在
    facility
    Facility.query.filter(Facility.id.in_(facility)).all()
    10/提交数据到数据库中,如果发生异常需要进行回滚
    11/返回结果,需要返回house.id

    :return:
    """
    # 获取用户身份信息
    user_id = g.user_id
    # 获取房屋的参数信息
    house_data = request.get_json()
    # 校验参数的存在
    if not house_data:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    # 获取详细的房屋参数信息,房屋的基本信息
    title = house_data.get('title') # 房屋名称
    price = house_data.get('price') # 房屋价格
    area_id = house_data.get('area_id') # 房屋区域
    address = house_data.get('address') # 详细地址
    room_count = house_data.get('room_count') # 房屋数目
    acreage = house_data.get('acreage') # 房屋面积
    unit = house_data.get('unit') # 房屋户型
    capacity = house_data.get('capacity') # 适住人数
    beds = house_data.get('beds') # 卧床配置
    deposit = house_data.get('deposit') # 房屋押金
    min_days = house_data.get('min_days') # 最少入住天数
    max_days = house_data.get('max_days') # 最多入住天数
    # 校验参数的完整性
    if not all([title,price,area_id,address,room_count,acreage,unit,capacity,beds,deposit,min_days,max_days]):
        return jsonify(errno=RET.PARAMERR,errmsg='参数不完整')
    # 对金额进行单位转换,前端一般使用元为单位,数据库中存储以分未单位
    try:
        price = int(float(price) * 100)
        deposit = int(float(deposit) *100)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR,errmsg='价格转换错误')
    # 构造模型类对象,准备存储房屋数据
    house = House()
    house.user_id = user_id
    house.title = title
    house.price = price
    house.area_id = area_id
    house.address = address
    house.room_count = room_count
    house.acreage = acreage
    house.unit = unit
    house.capacity = capacity
    house.beds = beds
    house.deposit = deposit
    house.min_days = min_days
    house.max_days = max_days
    # 尝试获取配套设施信息
    facility = house_data.get('facility')
    # 如果存在配套设施,需要对配套设施的编号进行过滤,确认配套设施存在
    if facility:
        try:
            facilities = Facility.query.filter(Facility.id.in_(facility)).all()
            # 保存配套设施
            house.facilities = facilities
        except Exception as e:
            current_app.logger.error(e)
            return jsonify(errno=RET.DBERR,errmsg='查询配套设施失败')
    # 提交数据到数据库中
    try:
        db.session.add(house)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存房屋数据失败')
    # 返回结果house.id
    return jsonify(errno=RET.OK,errmsg='OK',data={'house_id':house.id})


@api.route('/houses/<int:house_id>/images',methods=['POST'])
@login_required
def save_house_image(house_id):
    """
    保存房屋图片
    1/获取参数,request.files.get('house_image')
    2/校验图片参数存在
    3/根据house_id查询数据库,确认房屋的存在
    4/校验查询结果
    5/读取图片数据
    6/调用七牛云接口,上传房屋图片
    7/构造模型类对象,
    house_image = HouseImage()
    db.session.add(house_image)
    8/判断房屋主图片是否设置,如未设置,默认添加用户上传的第一张房屋图片为主图片
        if not house.index_image_url:
            house.index_image_url = image_name
            db.session.add(house)
    9/提交数据到数据库中
    10/拼接图片路径,七牛云的外链域名和图片名称
    11/返回结果
    :param house_id:
    :return:
    """
    # 获取图片参数
    image = request.files.get('house_image')
    # 校验参数的存在
    if not image:
        return jsonify(errno=RET.PARAMERR,errmsg='图片未上传')
    # 根据house_id查询数据库,确认房屋的存在
    try:
        house = House.query.get(house_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询房屋数据失败')
    # 校验查询结果
    if not house:
        return jsonify(errno=RET.NODATA,errmsg='无房屋数据')
    # 读取图片数据
    image_data = image.read()
    # 调用七牛云接口,上传房屋图片
    try:
        image_name = storage(image_data)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR,errmsg='上传房屋图片失败')
    # 构造HouseImage模型类对象,保存房屋图片
    house_image = HouseImage()
    house_image.house_id = house_id
    house_image.url = image_name
    # 把房屋图片数据存入数据库会话对象中
    db.session.add(house_image)
    # 判断房屋主图片是否设置
    if not house.index_image_url:
        house.index_image_url = image_name
        # 把房屋图片数据存入数据库会话对象中
        db.session.add(house)
    # 提交数据到数据库中
    try:
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存房屋图片失败')
    # 拼接图片绝对路径
    image_url = constants.QINIU_DOMIN_PREFIX + image_name
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data={'url':image_url})


@api.route('/user/houses',methods=['GET'])
@login_required
def get_user_houses():
    """
    获取用户发布的房屋信息
    1/获取用户的身份信息,user_id
    2/根据user_id查询数据库,确认用户的存在
    3/通过反向引用,获取该用户发布的房屋信息,因为用户和房屋之间是一对多的关系
    4/定义容器,存储查询结果
    5/判断如果有房屋数据,遍历查询结果
    6/返回结果
    :return:
    """
    # 获取用户身份id
    user_id = g.user_id
    # 根据user_id查询mysql数据库
    try:
        user = User.query.get(user_id)
        # 使用反向引用,获取该用户发布的房屋信息
        houses = user.houses
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询用户的房屋信息失败')
    # 定义容器,存储查询结果
    houses_list = []
    # 如果有数据,遍历查询结果
    if houses:
        for house in houses:
            houses_list.append(house.to_basic_dict())
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data={'houses':houses_list})



@api.route('/houses/index',methods=['GET'])
def get_houses_index():
    """
    获取房屋首页幻灯片信息:缓存-----磁盘-----缓存
    1/尝试从redis缓存中获取幻灯片数据
    2/校验结果,如果有数据,记录访问的时间,返回结果
    3/查询mysql数据库
    默认按照房屋成交量从高到低排序查询,需要分页分出五套房屋
    4/校验查询结果
    5/定义容器,遍历存储查询结果,判断是否设置房屋主图片,如未设置默认不添加
    6/对房屋数据进行序列化,转成json
    7/把房屋数据存入到缓存中
    8/返回结果

    :return:
    """
    # 尝试从redis中获取房屋信息
    try:
        ret = redis_store.get('home_page_data')
    except Exception as e:
        current_app.logger.error(e)
        ret = None
    # 判断获取结果,如果有数据,记录访问redis数据库的时间,返回结果
    if ret:
        current_app.logger.info('hit house index info redis')
        return '{"errno":0,"errmsg":"OK","data":%s}' % ret
    # 查询mysql数据库
    try:
        # 查询房屋表,默认按照成交量从高到低排序查询,返回五条数据
        houses = House.query.order_by(House.order_count.desc()).limit(constants.HOME_PAGE_MAX_HOUSES)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='获取房屋数据失败')
    # 校验查询结果,
    if not houses:
        return jsonify(errno=RET.NODATA,errmsg='无房屋数据')
    # 定义容器,遍历查询结果,添加数据
    houses_list = []
    # 需要对房屋主图片是否设置进行判断
    for house in houses:
        if not house.index_image_url:
            continue
        houses_list.append(house.to_basic_dict())
    # 序列化数据,转成json
    houses_json = json.dumps(houses_list)
    # 把房屋数据存入redis缓存中
    try:
        redis_store.setex('home_page_data',constants.HOME_PAGE_DATA_REDIS_EXPIRES,houses_json)
    except Exception as e:
        current_app.logger.error(e)
    # 构造响应报文,返回结果
    resp = '{"errno":0,"errmsg":"OK","data":%s}'% houses_json
    return resp


@api.route('/houses/<int:house_id>',methods=['GET'])
def get_house_detail(house_id):
    """
    获取房屋详情数据:缓存-----磁盘-----缓存
    1/尝试确认用户身份,把用户分成两类,登陆用户获取user_id,未登陆用户给默认值-1,
    session.get('user_id','-1')
    2/校验house_id参数存在
    3/操作redis数据库,尝试获取房屋详情信息
    4/判断获取结果,如果有数据,记录访问redis的时间,返回json数据
    5/查询mysql数据库
    House.query.get(house_id)
    6/校验查询结果,确认房屋的存在
    7/调用模型类中的to_full_dict(),需要进行异常处理
    8/对房屋详情数据进行序列化,存入redis缓存中
    9/构造响应数据
    10/返回结果,user_id和房屋详情数据
    :return:
    """
    # 尝试获取用户身份,如果用户未登陆默认-1
    user_id = session.get('user_id','-1')
    # 校验house_id存在
    if not house_id:
        return jsonify(errno=RET.PARAMERR,errmsg='参数缺失')
    # 根据house_id,尝试从redis获取房屋详情数据
    try:
        ret = redis_store.get('house_info_%s' % house_id)
    except Exception as e:
        current_app.logger.error(e)
        ret = None
    # 判断结果,如果有数据,留下访问redis数据库的记录
    if ret:
        current_app.logger.info('hit house detail info redis')
        return '{"errno":0,"errmsg":"OK","data":{"user_id":%s,"house":%s}}' %(user_id,ret)
    # 查询mysql数据库,确认房屋的存在
    try:
        house = House.query.get(house_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询房屋数据失败')
    # 校验查询结果
    if not house:
        return jsonify(errno=RET.NODATA,errmsg='无房屋数据')
    # 调用模型类中方法,获取房屋详情数据
    try:
        house_data = house.to_full_dict()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='获取房屋详情数据失败')
    # 序列化数据,转成json
    house_json = json.dumps(house_data)
    # 把房屋详情数据存入到redis缓存中
    try:
        redis_store.setex('house_info_%s' % house_id,constants.HOUSE_DETAIL_REDIS_EXPIRE_SECOND,house_json)
    except Exception as e:
        current_app.logger.error(e)
    # 构造响应报文
    resp = '{"errno":0,"errmsg":"OK","data":{"user_id":%s,"house":%s}}' %(user_id,house_json)
    # 返回结果
    return resp


@api.route('/houses',methods=['GET'])
def get_houses_list():
    """
    获取房屋列表信息
    缓存----磁盘-----缓存
    获取参数/校验参数/查询数据/返回结果
    1/尝试获取参数
    area_id,start_date_str,end_date_str,sort_key(需要给默认值),page(需要默认值)
    2/对日期参数进行格式化,datetime模块,strptime(start_date_str,'%Y-%m-%d')
    3/确认用户选择开始日期和结束日期至少是1天,开始日期小于等于结束日期
    4/对页数进行格式化转换,page = int(page)
    5/尝试从redis数据库中,获取房屋列表信息
    6/构造键:因为不同的页数和不同日期或区域,对应的是不同的房屋,需要使用hash数据类型
    redis_key = 'houses_%s_%s_%s_%s' %(area_id,start_date_str,end_date_str,sort_key)
    7/判断获取结果,如果有数据,记录访问的的时间,直接返回
    8/查询mysql数据库
    9/定义容器,存储查询的过滤条件
    params_filter = [],过滤条件里存储的应该是真实的区域信息,和满足日期条件的房屋
    10/对满足条件的房屋数据,进行排序操作:
    booking/price-inc/price-des/new
    houses = House.query.filter(*params_filter).order_by(House.create_time.desc())
    11/对排序后的房屋数据进行分页操作,paginate方法返回的分页的房屋数据,分页后的总页数
    houses_page = houses.paginate(page,每页的条目数,False)
    houses_list = houses_page.items 分页后的房屋数据
    total_page = houses_page.pages 分页后的总页数
    12/定义容器,遍历分页后的房屋数据,调用模型类中to_basic_dict()
    13/构造响应报文
    resp = {"errno":0,"errmsg":"OK","data":{"houses":houses_dict_list,"total_page":total_page,"current_page":page}}
    14/对响应数据进行序列化,转成json,存入到缓存中
    resp_json = json.dumps(resp)
    15/判断用户请求的页数小于等于分页后的总页数
    16/多条数据写入到redis数据库中,需要使用事务
    pip = redis_store.pipeline()
    pip.multi() 开启事务
    pip.hset(redis_key,page,resp_json) # 存储数据
    pip.expire(redis_key,过期时间) # 设置过期时间
    pip.execute() # 执行事务
    17/返回结果
    :return:
    """
    # 尝试获取参数,aid,sd,ed,sk,p,区域信息/开始日期/结束日期/排序条件/页数
    area_id = request.args.get('aid','')
    start_date_str = request.args.get('sd','')
    end_date_str = request.args.get('ed','')
    # 如果用户未传排序条件,默认排序new,房屋发布时间
    sort_key = request.args.get('sk','new')
    # 如果用户未传具体的页数,默认加载第一页
    page = request.args.get('p','1')
    # 对日期进行格式化,因为需要对日期进行比较
    try:
        # 存储格式化后的日期
        start_date,end_date = None,None
        # 判断用户如果有开始日期或结束日期
        if start_date_str:
            start_date = datetime.datetime.strptime(start_date_str,'%Y-%m-%d')
        if end_date_str:
            end_date = datetime.datetime.strptime(end_date_str,'%Y-%m-%d')
        # 确认用户选择的日期必须至少是1天,
        if start_date_str and end_date_str:
            assert start_date <= end_date
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.PARAMERR,errmsg='日期参数错误')
    # 对页数进行格式化
    try:
        page = int(page)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.PARAMERR,errmsg='页数参数错误')
    # 尝试从redis中获取缓存的房屋列表信息,一个键对应多条数据的存储,需要使用hash数据类型
    try:
        redis_key = 'houses_%s_%s_%s_%s' % (area_id,start_date_str,end_date_str,sort_key)
        ret = redis_store.hget(redis_key,page)
    except Exception as e:
        current_app.logger.error(e)
        ret = None
    # 判断获取结果,如果有数据,记录访问的时间,直接返回结果
    if ret:
        current_app.logger.info('hit houses list info redis')
        return ret
    # 查询mysql数据库
    try:
        # 存储查询的过滤条件
        params_filter = []
        # 判断区域信息存在
        if area_id:
            """
            a=[1,2,3]
            b=1
            a.append(a==b)
            a=[1,2,3,false]
            b=[1,2,3]
            a=[1,2,3,true]
            """
            params_filter.append(House.area_id == area_id) # 返回的是对象
        # 对日期进行判断,如果用户选择了开始日期和结束日期
        if start_date and end_date:
            # 查询日期有冲突的订单信息
            conflict_orders = Order.query.filter(Order.begin_date<=end_date,Order.end_date>=start_date).all()
            # 遍历有冲突的订单,获取的是有冲突的房屋
            conflict_houses_id = [order.house_id for order in conflict_orders]
            # 判断有冲突的房屋如果存在
            if conflict_houses_id:
                # 对有冲突的房屋进行取反,获取不冲突的房屋
                params_filter.append(House.id.notin_(conflict_houses_id))
        # 如果用户只选择了开始日期
        elif start_date:
            # 查询有冲突的订单
            conflict_orders = Order.query.filter(Order.end_date>=start_date).all()
            # 获取有冲突的房屋
            conflict_houses_id = [order.house_id for order in conflict_orders]
            if conflict_houses_id:
                params_filter.append(House.id.notin_(conflict_houses_id))
        # 如果用户只选择了结束日期
        elif end_date:
            conflict_orders = Order.query.filter(Order.begin_date<=end_date).all()
            conflict_houses_id = [order.house_id for order in conflict_orders]
            if conflict_houses_id:
                params_filter.append(House.id.notin_(conflict_houses_id))
        # 判断排序条件,booking/price-inc/price-des/new
        if 'booking' == sort_key:
            houses = House.query.filter(*params_filter).order_by(House.order_count.desc())
        elif 'price-inc' == sort_key:
            houses = House.query.filter(*params_filter).order_by(House.price.asc())
        elif 'price-des' == sort_key:
            houses = House.query.filter(*params_filter).order_by(House.price.desc())
        # 如果用户未选择排序条件,默认按照房屋发布时间进行排序
        else:
            houses = House.query.filter(*params_filter).order_by(House.create_time.desc())
        # 对排序后的房屋数据进行分页,page表示页数/每页条目数/False分页发生异常不报错
        houses_page = houses.paginate(page,constants.HOUSE_LIST_PAGE_CAPACITY,False)
        # 获取分页后的房屋数据,以及分页后的总页数
        houses_list = houses_page.items # 分页后的房屋数据
        total_page = houses_page.pages # 分页后的总页数
        # 定义容器,遍历分页房屋数据,调用模型类中to_basic_dict()
        houses_dict_list = []
        for house in houses_list:
            houses_dict_list.append(house.to_basic_dict())
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='获取房屋列表数据失败')
    # 构造响应报文
    resp = {"errno":0,"errmsg":"OK","data":{"houses":houses_dict_list,"total_page":total_page,"current_page":page}}
    # 序列化数据,准备存入缓存中
    resp_json = json.dumps(resp)
    # 判断用户请求的页数必须小于等于分页后的总页数,即用户请求的页数有数据
    if page <= total_page:
        # 构造redis_key
        redis_key = 'houses_%s_%s_%s_%s' % (area_id,start_date_str,end_date_str,sort_key)
        # 多条数据往redis中存储,为了确保有效期的一致,需要使用事务
        pip = redis_store.pipeline()
        try:
            # 开启事务
            pip.multi()
            # 存储数据
            pip.hset(redis_key,page,resp_json)
            # 设置过期时间
            pip.expire(redis_key,constants.HOUSE_LIST_REDIS_EXPIRES)
            # 执行事务
            pip.execute()
        except Exception as e:
            current_app.logger.error(e)
    # 返回结果
    return resp_json






















