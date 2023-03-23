from PIL import Image
from PIL.ImageDraw import ImageDraw
from PIL import ImageFont
import random

class ImageWall:
    def __init__(self, size, dim, canvasmode, color) -> None:
        assert isinstance(size, tuple) and len(size) == 2, 'size应是2个元素的元组类型'
        assert isinstance(dim, tuple) and len(dim) == 2, 'dim应是2个元素的元组类型'
        assert canvasmode in ['RGB', 'RGBA'], "canvasmode应设置为'RGB'或'RGBA'"
        assert isinstance(color, tuple) and len(color) == 3, 'color应是3个元素的元组类型'
        self.__size = size
        self.__dim = dim
        self.__width, self.__height = self.__size
        self.__columns, self.__lines = self.__dim
        self.__canvasmode = canvasmode
        self.__color = color
        self.__cx = self.__width // self.__columns
        self.__cy = self.__height // self.__lines
        self.__im = Image.new(self.__canvasmode, self.__size, self.__color)
        self.__imdraw = ImageDraw(self.__im, self.__canvasmode)
        self.__fnt = ImageFont.truetype("arial.ttf", 15)

    def __get_cell(self, x, y):
        if not(0 <= x <= self.__columns) or not(0 <= y <= self.__lines):
            return ()
        return(x * self.__cx, y * self.__cy, (x + 1) * self.__cx, (y + 1) * self.__cy)
    
    def get_imagewall_info(self):
        return ((self.__width, self.__height), (self.__columns, self.__lines), self.__canvasmode)

    def save(self, out):
        self.__im.save(out)


    def draw_grids(self, color, width):
        cx = range(0, self.__width, self.__width // self.__columns)
        ps1 = list(zip(cx, [0 for i in range(self.__columns)]))
        ps1.append((self.__width - width, 0))
        ps2 = list(zip(cx, [self.__height for i in range(self.__columns )]))
        ps2.append((self.__width - width, self.__height))
        for i in zip(ps1, ps2):
            self.__imdraw.line(list(i), color, width)
        cy = range(0, self.__height, self.__height // self.__lines)
        ps1 = list(zip([0 for i in range(self.__lines)], cy))
        ps1.append((0, self.__height - width))
        ps2 = list(zip([self.__width for i in range(self.__lines)], cy))
        ps2.append((self.__width, self.__height - width))
        for i in zip(ps1, ps2):
            self.__imdraw.line(list(i), color, width)

    def draw_cell(self, im, title, x, y):
        assert isinstance(im, Image.Image), "im必须是Image类型"
        assert isinstance(title, (str, None)), "title必须是tr或None类型"
        region = self.__get_cell(x, y)
        if not region:
            return 
        if im.size[0] > self.__cx or im.size[1] > self.__cy:
            im = im.resize((min(self.__cx, im.size[0]), min(self.__cy, im.size[1])))
        x = (self.__cx - im.size[0]) // 2
        y = (self.__cy - im.size[1]) // 2
        # self.__im.paste(im, (region[0], region[1]))
        self.__im.paste(im, (region[0] + x, region[1] + y))
        if title:
            self.__imdraw.text((region[0] + 2, region[1] + 2), title, (0, 0, 0), self.__fnt)


    def draw_wall(self, imgs, titles):
        assert isinstance(imgs, list), "imgs应是一个列表类型"
        assert isinstance(titles, list), "titles应是一个列表类型"
        length1 = len(imgs)
        length2 = len(titles)
        if length2 < length1:
            titles.extend([None for i in range(length1 - length2)])
        y = -1
        for i in range(length1):
            x = i % self.__columns
            if x == 0:
                y += 1
            self.draw_cell(imgs[i], titles[i], x, y)

    def show_wall(self):
        self.__im.show()

def image_create(num, size):
    assert isinstance(num, int), "num必须是整数"
    assert isinstance(size, tuple) and len(size) == 2, "size必须是长度为2的元组"
    imgs = list()
    titles = list()
    for i in range(num):
        c1 = random.randint(0, 255)
        c2 = random.randint(0, 255)
        c3 = random.randint(0, 255)
        im = Image.new('RGB', size, (c1, c2, c3))
        imgs.append(im)
        titles.append(f'IMG{i}')
    return imgs, titles

def test():
    imgwall = ImageWall((1400, 1400), (10, 14), 'RGB', (255, 255, 255),)
    imgs, titles = image_create(140, (140, 100))
    imgwall.draw_wall(imgs, titles)
    imgwall.draw_grids((0, 0, 0), 2)
    imgwall.save('./tmp.jpeg')

if __name__ == "__main__":
    test()